// Optional local LLM: Qwen2.5-0.5B-Instruct running in the browser via Transformers.js
// (ONNX Runtime, WebGPU with WASM/CPU fallback). No external inference API is used;
// the first load downloads model files, which the browser caches for later use.
import { buildChatContext } from "./srsContext.js";

export const MODEL_ID = "onnx-community/Qwen2.5-0.5B-Instruct";
const TRANSFORMERS_CDN = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0";

export const CHAT_SYSTEM_PROMPT = `You are ReqValidator Local, a software requirements engineering assistant.
You help users understand, review, improve, and validate Software Requirements Specifications.
You have access to the current project's requirements and the available analysis results in PROJECT CONTEXT.
Always ground your answers in the supplied project context and refer to requirement IDs.
When asked to rewrite requirements, preserve the original intent and use [TBD] for missing information.
When asked for acceptance criteria, provide Given-When-Then scenarios.
When asked for test cases, include positive, negative, and boundary cases where relevant.
When asked about quality scores, explain the actual findings that contributed to the score.
If the answer is not in the project context, say so, ask a clarifying question, and label general software engineering advice as general guidance.
Never invent requirements, scores, test results, stakeholder decisions, or analysis findings.
Be conversational, concise by default, and detailed when requested. Use recent conversation history to understand follow-up questions.`;

let transformersPromise;
let pipelinePromise;
let loadedDevice = null;
let busy = false;
let stopper = null;

function loadTransformers() {
  if (!transformersPromise) {
    transformersPromise = import(/* @vite-ignore */ TRANSFORMERS_CDN).catch((error) => {
      transformersPromise = undefined;
      throw new Error(`Could not load the local AI runtime. An internet connection is needed the first time. (${error.message || error})`);
    });
  }
  return transformersPromise;
}

function hasWebGpu() {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

async function createPipeline(onProgress, forceWasm = false) {
  const { pipeline, env } = await loadTransformers();
  env.allowLocalModels = false;
  env.useBrowserCache = true;
  const progress_callback = (event) => {
    if (event?.status === "progress" && typeof event.progress === "number") {
      onProgress?.({ stage: "download", percent: Math.round(event.progress), message: `Downloading ${event.file || "model files"}: ${Math.round(event.progress)}%` });
    } else if (event?.status === "ready") {
      onProgress?.({ stage: "ready", percent: 100, message: "Model loaded." });
    }
  };
  const load = (device) => pipeline("text-generation", MODEL_ID, { device, dtype: "q4", progress_callback });

  if (!forceWasm && hasWebGpu()) {
    try {
      onProgress?.({ stage: "init", message: "Loading model with WebGPU acceleration..." });
      const generator = await load("webgpu");
      loadedDevice = "webgpu";
      return generator;
    } catch (error) {
      console.warn("WebGPU unavailable; falling back to WASM:", error);
    }
  }
  onProgress?.({ stage: "init", message: "Loading model in CPU/WASM mode (slower)..." });
  const generator = await load("wasm");
  loadedDevice = "wasm";
  return generator;
}

function getPipeline(onProgress) {
  if (!pipelinePromise) {
    pipelinePromise = createPipeline(onProgress).catch((error) => {
      pipelinePromise = undefined;
      throw error;
    });
  }
  return pipelinePromise;
}

export function isLocalModelLoaded() {
  return Boolean(pipelinePromise && loadedDevice);
}

export function getLocalModelDevice() {
  return loadedDevice;
}

export async function loadLocalModel(onProgress) {
  await getPipeline(onProgress);
  return loadedDevice;
}

export function cancelLocalGeneration() {
  stopper?.interrupt?.();
}

function cleanOutput(output) {
  const generated = Array.isArray(output) ? output[0]?.generated_text : output?.generated_text;
  if (typeof generated === "string") {
    return generated.replace(/^.*?<\|im_start\|>assistant\s*/s, "").replace(/<\|im_end\|>[\s\S]*$/s, "").trim();
  }
  if (Array.isArray(generated)) {
    const last = [...generated].reverse().find((item) => item?.role === "assistant");
    return typeof last?.content === "string" ? last.content.trim() : "";
  }
  return "";
}

async function generate(messages, { maxNewTokens, onToken, onProgress }) {
  if (busy) throw new Error("The local model is already generating a response. Please wait or stop it.");
  busy = true;
  try {
    const { TextStreamer, InterruptableStoppingCriteria } = await loadTransformers();
    let generator = await getPipeline(onProgress);
    const run = async (gen) => {
      stopper = new InterruptableStoppingCriteria();
      let streamed = "";
      const streamer = new TextStreamer(gen.tokenizer, {
        skip_prompt: true,
        skip_special_tokens: true,
        callback_function: (text) => {
          streamed += text;
          onToken?.(streamed);
        },
      });
      const output = await gen(messages, {
        max_new_tokens: maxNewTokens,
        do_sample: false,
        repetition_penalty: 1.1,
        streamer,
        stopping_criteria: stopper,
      });
      return cleanOutput(output) || streamed.trim();
    };
    try {
      return await run(generator);
    } catch (error) {
      if (loadedDevice !== "webgpu") throw error;
      // WebGPU can initialise but fail during execution (lost device, out of memory).
      console.warn("WebGPU execution failed; retrying on CPU/WASM:", error);
      onProgress?.({ stage: "fallback", message: "GPU execution failed. Switching to CPU/WASM mode..." });
      pipelinePromise = createPipeline(onProgress, true);
      generator = await pipelinePromise;
      return await run(generator);
    }
  } catch (error) {
    const message = String(error?.message || error);
    if (/memory|allocation|OOM/i.test(message)) {
      throw new Error("The device ran out of memory while running the local model. Close other tabs and retry.", { cause: error });
    }
    throw error;
  } finally {
    busy = false;
    stopper = null;
  }
}

/**
 * Chat with Qwen using the whole SRS: relevant requirements are retrieved for
 * each question so large documents fit the model's context window.
 */
export async function generateSrsChatReply(items, history, question, onProgress, options = {}) {
  const { context, note } = buildChatContext(items, history, question, options.project);
  const recent = (Array.isArray(history) ? history : []).slice(-8).map((m) => ({
    role: m.role === "assistant" ? "assistant" : "user",
    content: String(m.content || "").slice(0, 1200),
  }));
  const messages = [
    { role: "system", content: `${CHAT_SYSTEM_PROMPT}\n\nPROJECT CONTEXT:\n${context}` },
    ...recent,
    { role: "user", content: String(question || "").slice(0, 1500) },
  ];
  onProgress?.({ stage: "generate", message: "Generating an answer on this device..." });
  const reply = await generate(messages, { maxNewTokens: options.maxNewTokens || 512, onToken: options.onToken, onProgress });
  if (!reply) throw new Error("The local model returned an empty answer. Please try again.");
  return { reply, note };
}

/** Optional deep review of selected requirements (shares the loaded model with chat). */
export async function generateSrsReview(items, onProgress, options = {}) {
  if (!Array.isArray(items) || items.length === 0) throw new Error("At least one requirement is needed.");
  const records = items.map((item, index) => {
    const a = item.analysis || {};
    return `${item.requirement_id || `REQ-${index + 1}`}: "${String(item.requirement || "").slice(0, 400)}"\n` +
      `  Rule-engine score: ${a.quality_score ?? "n/a"}; type: ${a.classification || "n/a"}; findings: ${(a.issues || []).slice(0, 4).join(" | ") || "none"}`;
  }).join("\n");
  const messages = [
    { role: "system", content: "You are a senior requirements analyst and QA engineer. Review only the supplied requirements and their rule-engine findings. Do not invent business rules, numbers or stakeholder decisions; use [TBD]. For each requirement give: interpretation, key problems (quote the phrase), an improved draft, Given/When/Then acceptance criteria, and positive/negative/boundary test ideas. Finish with cross-requirement observations. Use Markdown headings and bullets." },
    { role: "user", content: `Review these requirements:\n${records}` },
  ];
  onProgress?.({ stage: "generate", message: "Generating the review on this device..." });
  const report = await generate(messages, { maxNewTokens: options.maxNewTokens || 1200, onToken: options.onToken, onProgress });
  if (!report || report.length < 40) throw new Error("The local model returned an incomplete review. Please retry.");
  return report;
}
