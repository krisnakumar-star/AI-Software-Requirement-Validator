const MODEL_ID = "onnx-community/Qwen2.5-0.5B-Instruct";
const TRANSFORMERS_CDN = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0";

let pipelinePromise;

async function createPipeline(onProgress, forceWasm = false) {
  // Import at runtime so the application bundle does not need a server-side model package.
  const { pipeline, env } = await import(/* @vite-ignore */ TRANSFORMERS_CDN);
  env.allowLocalModels = false;
  env.useBrowserCache = true;

  const progress_callback = (event) => {
    if (event?.status === "progress" && typeof event.progress === "number") {
      onProgress?.(`Downloading model files: ${Math.round(event.progress)}%`);
    } else if (event?.status === "initiate") {
      onProgress?.(`Downloading ${event.file || "model files"}...`);
    } else if (event?.status === "ready") {
      onProgress?.("Model loaded. Preparing the review...");
    }
  };

  if (forceWasm) {
    onProgress?.("Using the stable CPU/WASM mode because WebGPU is unavailable on this device...");
    return await pipeline("text-generation", MODEL_ID, {
      device: "wasm",
      dtype: "q4",
      progress_callback,
    });
  }

  try {
    onProgress?.("Trying WebGPU acceleration...");
    return await pipeline("text-generation", MODEL_ID, {
      device: "webgpu",
      dtype: "q4",
      progress_callback,
    });
  } catch (webgpuError) {
    console.warn("WebGPU unavailable; falling back to WASM:", webgpuError);
    onProgress?.("WebGPU unavailable. Loading the CPU/WASM version...");
    return await pipeline("text-generation", MODEL_ID, {
      device: "wasm",
      dtype: "q4",
      progress_callback,
    });
  }
}

async function getPipeline(onProgress) {
  if (!pipelinePromise) {
    pipelinePromise = createPipeline(onProgress).catch((error) => {
      pipelinePromise = undefined;
      throw error;
    });
  }
  return pipelinePromise;
}

async function runWithWebGpuRecovery(prompt, generationOptions, onProgress) {
  let generator = await getPipeline(onProgress);
  try {
    return await generator(prompt, generationOptions);
  } catch (webgpuError) {
    // WebGPU can initialize successfully but fail later during ONNX execution
    // (for example, a lost GPU device or invalid external instance).
    console.warn("Local model execution failed; retrying with CPU/WASM:", webgpuError);
    pipelinePromise = undefined;
    onProgress?.("GPU execution failed. Switching to CPU/WASM and retrying; this may be slower...");
    generator = await createPipeline(onProgress, true);
    pipelinePromise = Promise.resolve(generator);
    try {
      return await generator(prompt, generationOptions);
    } catch (wasmError) {
      pipelinePromise = undefined;
      throw new Error(`The local model could not run on this device in WebGPU or CPU mode. Try refreshing the page or using a device with more available memory. Details: ${wasmError.message || wasmError}`);
    }
  }
}

function cleanOutput(output) {
  const generated = Array.isArray(output) ? output[0]?.generated_text : output?.generated_text;
  if (typeof generated === "string") {
    return generated.replace(/^.*?<\|im_start\|>assistant\s*/s, "").replace(/<\|im_end\|>[\s\S]*$/s, "").trim();
  }
  if (Array.isArray(generated)) {
    const lastAssistant = [...generated].reverse().find((item) => item?.role === "assistant");
    return typeof lastAssistant?.content === "string" ? lastAssistant.content.trim() : JSON.stringify(generated);
  }
  return typeof generated === "undefined" ? JSON.stringify(output) : String(generated);
}

export async function generateSrsReview(items, onProgress) {
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("At least one requirement is needed.");
  }

  const promptData = items.map((item, index) => ({
    id: index + 1,
    requirement: String(item.requirement || ""),
    existing_rule_findings: item.analysis?.issues || [],
    existing_recommendations: item.analysis?.missing_information || item.analysis?.suggestions || [],
    rule_based_score: item.analysis?.quality_score ?? item.analysis?.qualityScore ?? null,
    detected_type: item.analysis?.classification || "Not classified",
  }));

  const system = `You are a senior software requirements analyst and QA engineer. Review the supplied SRS requirements carefully. Produce a useful, detailed, professional review grounded ONLY in the supplied requirement text and existing findings. Do not claim that an assumption is a fact. Do not invent business rules, legal obligations, numeric thresholds, technologies, or stakeholder decisions. Mark uncertain conclusions as questions or possibilities. Avoid generic filler. Be specific to each requirement.

For every requirement, write:
1. Plain-language interpretation of what it asks for.
2. Requirement type and relevant quality attributes.
3. What is already good.
4. Specific defects or ambiguity, quoting the exact phrase that caused concern.
5. Why each defect matters to implementation or testing.
6. Missing preconditions, actors, inputs, outputs, permissions, data rules, exception cases, and measurable targets, only where relevant.
7. Clarifying questions for the product owner.
8. A careful improved requirement draft. Use [TBD: ...] for unknown values; never fabricate them.
9. Given/When/Then acceptance criteria with TBD placeholders where details are missing.
10. Positive, negative, boundary, and failure-path test ideas.
11. A concise final verdict and priority.

Then provide cross-requirement observations if multiple requirements are supplied: possible duplication, dependency, terminology mismatch, and potential conflict. Do not declare conflict unless the text supports it. Keep the report readable with Markdown headings and bullets. This is an assistive review, not a certification.`;

  const user = `Review these requirement records:\n\n${JSON.stringify(promptData, null, 2)}`;
  const prompt = `<|im_start|>system\n${system}<|im_end|>\n<|im_start|>user\n${user}<|im_end|>\n<|im_start|>assistant\n`;

  onProgress?.("Generating the requirement review on this device...");
  const result = await runWithWebGpuRecovery(prompt, {
    max_new_tokens: 1200,
    do_sample: false,
    repetition_penalty: 1.08,
    return_full_text: false,
  });

  const report = cleanOutput(result);
  if (!report || report.length < 40) {
    throw new Error("The local model returned an empty or incomplete review. Please retry.");
  }
  return report;
}

export async function generateSrsChatReply(items, history, question, onProgress) {
  const safeItems = (Array.isArray(items) ? items : []).slice(0, 10).map((item, index) => ({
    id: index + 1,
    requirement: String(item.requirement || ""),
    score: item.analysis?.quality_score ?? null,
    classification: item.analysis?.classification || "Not classified",
    issues: item.analysis?.issues || [],
    ambiguities: item.analysis?.ambiguities || [],
    missing_information: item.analysis?.missing_information || [],
    suggested_rewrite: item.analysis?.suggested_rewrite || "",
    explanation: item.analysis?.explanation || "",
  }));
  const recentHistory = (Array.isArray(history) ? history : []).slice(-6).map((message) => ({
    role: message.role === "assistant" ? "assistant" : "user",
    content: String(message.content || "").slice(0, 1800),
  }));
  const system = `You are ReqValidator's SRS review assistant. Answer the user's question using the supplied project validation context. Be friendly, clear, concise, and practical. Explain technical terms simply when needed. Refer to requirement IDs or quoted requirement text where possible. If the context does not contain the answer, say what is missing and ask a useful follow-up; do not invent project facts, requirements, scores, or stakeholder decisions. You may give general software requirements guidance, but label it as general guidance. For requests to summarize, give a short structured summary. For requests to improve a requirement, preserve its intent and use [TBD] for unknown details. This is a focused project assistant, not a general-purpose chatbot.`;
  const prompt = `<|im_start|>system\n${system}\n\nPROJECT VALIDATION CONTEXT:\n${JSON.stringify(safeItems, null, 2)}<|im_end|>\n${recentHistory.map((m) => `<|im_start|>${m.role}\n${m.content}<|im_end|>`).join("\n")}\n<|im_start|>user\n${String(question || "").slice(0, 1200)}<|im_end|>\n<|im_start|>assistant\n`;
  onProgress?.("Thinking about your question using the project context...");
  const result = await runWithWebGpuRecovery(prompt, {
    max_new_tokens: 420,
    do_sample: false,
    repetition_penalty: 1.08,
    return_full_text: false,
  });
  const reply = cleanOutput(result);
  if (!reply || reply.length < 2) throw new Error("The local model returned an empty answer. Please try again.");
  return reply;
}
