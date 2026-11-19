package com.reqvalidator.backend.controller;

import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonProcessingException;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.reqvalidator.backend.model.Project;
import com.reqvalidator.backend.model.Requirement;
import com.reqvalidator.backend.repository.ProjectRepository;
import com.reqvalidator.backend.repository.RequirementRepository;
import com.reqvalidator.backend.service.LlmAnalysisService;

@RestController
@RequestMapping("/api/llm")
@CrossOrigin(origins = {"http://localhost:5173", "https://ai-software-requirement-validator.vercel.app"})
public class LlmAnalysisController {

    private static final Logger logger = LoggerFactory.getLogger(LlmAnalysisController.class);

    private final RequirementRepository requirementRepository;
    private final ProjectRepository projectRepository;
    private final LlmAnalysisService llmAnalysisService;
    private final ObjectMapper objectMapper;

    public LlmAnalysisController(
            RequirementRepository requirementRepository,
            ProjectRepository projectRepository,
            LlmAnalysisService llmAnalysisService,
            ObjectMapper objectMapper) {

        this.requirementRepository = requirementRepository;
        this.projectRepository = projectRepository;
        this.llmAnalysisService = llmAnalysisService;
        this.objectMapper = objectMapper;
    }

    // =========================================================
    // CHECK LLM SERVER HEALTH
    // =========================================================

    @GetMapping("/health")
    public ResponseEntity<?> checkLlmHealth() {

        try {

            llmAnalysisService.checkHealth();

            return ResponseEntity.ok(
                    Map.of(
                            "status", "UP",
                            "message", "LLM service is reachable."
                    )
            );

        } catch (Exception e) {

            return ResponseEntity
                    .status(503)
                    .body(
                            Map.of(
                                    "status", "DOWN",
                                    "message",
                                    "LLM service is currently unavailable."
                            )
                    );
        }
    }

    // =========================================================
    // ANALYZE PROJECT REQUIREMENTS WITH LLM
    // =========================================================

    @PostMapping(
            value = "/analyze/project/{projectId}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> analyzeProjectWithLlm(
            @PathVariable String projectId,
            Authentication authentication) {

        String authenticatedEmail = authentication.getName();

        // -----------------------------------------------------
        // Check project exists
        // -----------------------------------------------------

        Project project = projectRepository
                .findById(projectId)
                .orElse(null);

        if (project == null) {

            return ResponseEntity
                    .notFound()
                    .build();
        }

        // -----------------------------------------------------
        // Check project ownership
        // -----------------------------------------------------

        if (!authenticatedEmail.equalsIgnoreCase(
                project.getOwnerEmail())) {

            return ResponseEntity
                    .status(403)
                    .body(
                            Map.of(
                                    "status", 403,
                                    "error", "Forbidden",
                                    "message",
                                    "You do not have permission to access this project."
                            )
                    );
        }

        // -----------------------------------------------------
        // Get requirements belonging to this project
        // -----------------------------------------------------

        List<Requirement> requirements =
                requirementRepository.findByProjectId(projectId);

        if (requirements.isEmpty()) {

            return ResponseEntity
                    .badRequest()
                    .body(
                            Map.of(
                                    "status", 400,
                                    "error", "Bad Request",
                                    "message",
                                    "No requirements found for this project."
                            )
                    );
        }

        // -----------------------------------------------------
        // Extract only actual requirement text
        // -----------------------------------------------------

        List<Requirement> validRequirements = requirements.stream()
                .filter(item -> item.getRequirementText() != null && !item.getRequirementText().isBlank())
                .toList();

        if (validRequirements.isEmpty()) {

            return ResponseEntity
                    .badRequest()
                    .body(
                            Map.of(
                                    "status", 400,
                                    "error", "Bad Request",
                                    "message",
                                    "No valid requirement text found."
                            )
                    );
        }

        // -----------------------------------------------------
        // Send requirements to the configured FastAPI AI service
        // -----------------------------------------------------

        List<Map<String, String>> requestItems = validRequirements.stream().map(item -> {
            Map<String, String> requestItem = new HashMap<>();
            requestItem.put("requirement", item.getRequirementText());
            requestItem.put("source", project.getName());
            requestItem.put("section_number", item.getRequirementId());
            return requestItem;
        }).toList();

        String llmResponse = llmAnalysisService.analyzeRequirements(requestItems);
        Map<String, Object> normalizedResponse = normalizeBatchResponse(
                llmResponse,
                validRequirements
        );

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> normalizedResults =
                (List<Map<String, Object>>) normalizedResponse.get("results");
        for (int i = 0; i < normalizedResults.size(); i++) {
            @SuppressWarnings("unchecked")
            Map<String, Object> analysis =
                    (Map<String, Object>) normalizedResults.get(i).get("analysis");
            Requirement requirement = validRequirements.get(i);
            requirement.setAiAnalysis(analysis);
            requirementRepository.save(requirement);
        }

        // -----------------------------------------------------
        // Return LLM response
        // -----------------------------------------------------

        return ResponseEntity
                .ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(normalizedResponse);
    }

    private Map<String, Object> normalizeBatchResponse(
            String responseBody,
            List<Requirement> requirements) {

        JsonNode response;
        try {
            response = objectMapper.readTree(responseBody);
        } catch (JsonProcessingException exception) {
            logger.warn("FastAPI response validation failed: endpoint=/analyze-batch, reason=invalid JSON at line {}, column {}, exception={}",
                    exception.getLocation() == null ? -1 : exception.getLocation().getLineNr(),
                    exception.getLocation() == null ? -1 : exception.getLocation().getColumnNr(),
                    exception.getClass().getSimpleName());
            throw new IllegalStateException("AI service returned invalid JSON.");
        }
        if (response == null || !response.isObject()) {
            throw invalidResponse("response must be a JSON object");
        }

        JsonNode analyses = response.path("analyses");
        if (!analyses.isArray()) {
            // Accept the current FastAPI batch envelope (analyses with flattened fields)
            // and the legacy Spring-facing results envelope.
            analyses = response.path("results");
        }
        if (!analyses.isArray() || analyses.size() != requirements.size()) {
            throw invalidResponse("analysis count does not match request count");
        }

        List<Map<String, Object>> results = new ArrayList<>();
        for (int i = 0; i < analyses.size(); i++) {
            JsonNode item = analyses.get(i);
            if (item.has("requirement_number")
                    && item.path("requirement_number").asInt(-1) != i + 1) {
                throw invalidResponse("analysis order is invalid at item " + (i + 1));
            }

            String returnedRequirement = item.path("requirement").asText(
                    requirements.get(i).getRequirementText()
            );
            if (!requirements.get(i).getRequirementText().equals(returnedRequirement)) {
                throw invalidResponse("requirement does not match request at item " + (i + 1));
            }

            JsonNode analysisNode = item.path("analysis");
            if (!analysisNode.isObject()) {
                analysisNode = item;
            }
            Map<String, Object> analysis = validateAnalysis(analysisNode);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("requirement_id", requirements.get(i).getRequirementId());
            result.put("requirement", requirements.get(i).getRequirementText());
            result.put("analysis", analysis);
            results.add(result);
        }

        Map<String, Object> normalized = new LinkedHashMap<>();
        normalized.put("status", response.path("status").asText("success"));
        if (response.hasNonNull("provider")) {
            normalized.put("provider", response.path("provider").asText());
        }
        if (response.hasNonNull("model")) {
            normalized.put("model", response.path("model").asText());
        }
        normalized.put("total_requirements", results.size());
        normalized.put("results", results);
        return normalized;
    }

    private Map<String, Object> validateAnalysis(JsonNode analysis) {
        String[] textFields = {
            "classification", "clarity", "completeness", "testability",
            "suggested_rewrite", "explanation"
        };
        String[] listFields = {"ambiguities", "missing_information", "issues"};

        JsonNode score = analysis.path("quality_score");
        if (!score.isIntegralNumber() || score.asInt() < 0 || score.asInt() > 100) {
            throw invalidResponse("quality_score must be an integer from 0 to 100");
        }
        for (String field : textFields) {
            if (!analysis.path(field).isTextual()) {
                throw invalidResponse(field + " must be a string");
            }
        }
        for (String field : listFields) {
            JsonNode values = analysis.path(field);
            if (!values.isArray() || !allText(values)) {
                throw invalidResponse(field + " must be a list of strings");
            }
        }

        Map<String, Object> validated = new LinkedHashMap<>();
        validated.put("quality_score", score.asInt());
        for (String field : textFields) {
            validated.put(field, analysis.path(field).asText());
        }
        for (String field : listFields) {
            validated.put(field, objectMapper.convertValue(
                    analysis.path(field), objectMapper.getTypeFactory().constructCollectionType(List.class, String.class)));
        }
        return validated;
    }

    private boolean allText(JsonNode values) {
        for (JsonNode value : values) {
            if (!value.isTextual()) {
                return false;
            }
        }
        return true;
    }

    private IllegalStateException invalidResponse(String reason) {
        logger.warn("FastAPI response validation failed: endpoint=/analyze-batch, reason={}", reason);
        return new IllegalStateException("AI service returned an invalid analysis response: " + reason + ".");
    }
}
