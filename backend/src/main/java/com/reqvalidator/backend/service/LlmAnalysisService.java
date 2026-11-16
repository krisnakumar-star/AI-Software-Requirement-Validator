
package com.reqvalidator.backend.service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.regex.Pattern;

@Service
public class LlmAnalysisService {

    private static final Logger logger = LoggerFactory.getLogger(LlmAnalysisService.class);
    private static final Pattern BEARER_TOKEN = Pattern.compile("(?i)(Bearer\\s+)[A-Za-z0-9._~+/-]+=*");
    private static final Pattern JWT_TOKEN = Pattern.compile("(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])");
    private static final Pattern CREDENTIAL = Pattern.compile("(?i)((?:api[_ -]?key|access[_ -]?token|authorization|secret)\\s*[:=]\\s*)[^\\s,;\\\"}]+");

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    @Value("${llm.api.url}")
    private String apiUrl;

    @Value("${llm.api.key}")
    private String apiKey;

    public LlmAnalysisService(
            @Value("${llm.api.connect-timeout:10000}") int connectTimeout,
            @Value("${llm.api.read-timeout:120000}") int readTimeout,
            ObjectMapper objectMapper) {
        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(connectTimeout);
        requestFactory.setReadTimeout(readTimeout);

        this.restClient = RestClient.builder()
                .requestFactory(requestFactory)
                .build();
        this.objectMapper = objectMapper;
    }

    // Analyze a single requirement
    public String analyzeRequirement(
            String requirement,
            String source,
            String sectionNumber) {

        Map<String, Object> request = new HashMap<>();
        request.put("requirement", requirement);
        request.put("source", source);
        request.put("section_number", sectionNumber);

        try {
            return restClient.post()
                    .uri(apiUrl + "/analyze")
                    .header("x-api-key", apiKey)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(String.class);

        } catch (RestClientException e) {
            throw translateFailure(e, "/analyze");
        }
    }

    // Analyze multiple requirements
    public String analyzeRequirements(
            List<Map<String, String>> requirements) {

        Map<String, Object> request = new HashMap<>();
        request.put("requirements", requirements);

        try {
            return restClient.post()
                    .uri(apiUrl + "/analyze-batch")
                    .header("x-api-key", apiKey)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(String.class);

        } catch (RestClientException e) {
            throw translateFailure(e, "/analyze-batch");
        }
    }

    // Check AI API health
    public String checkHealth() {
        try {
            return restClient.get()
                    .uri(apiUrl + "/health")
                    .retrieve()
                    .body(String.class);

        } catch (RestClientException e) {
            throw translateFailure(e, "/health");
        }
    }

    private IllegalStateException translateFailure(RestClientException exception, String endpoint) {
        if (exception instanceof HttpStatusCodeException httpException) {
            int status = httpException.getStatusCode().value();
            String responseBody = httpException.getResponseBodyAsString();
            logger.warn("FastAPI upstream HTTP error: status={}, endpoint={}, body={}",
                    status, endpoint, sanitizeForLog(responseBody));
            String detail = safeFastApiDetail(responseBody);
            if (detail != null) {
                return new IllegalStateException(detail);
            }
            if (status == 401 || status == 403) {
                return new IllegalStateException("AI service authentication failed. Check LLM_API_KEY.");
            }
            if (status == 429) {
                return new IllegalStateException("AI service is rate limiting requests. Please retry shortly.");
            }
            if (status == 504) {
                return new IllegalStateException("AI analysis timed out. Please retry.");
            }
            if (status >= 500) {
                return new IllegalStateException("AI analysis provider is unavailable. Please retry later.");
            }
            return new IllegalStateException("AI service rejected the analysis request.");
        }
        if (isTimeout(exception)) {
            logger.warn("FastAPI request timed out: endpoint={}, exception={}",
                    endpoint, exception.getClass().getSimpleName());
            return new IllegalStateException("AI service request timed out. Please retry.");
        }
        if (exception instanceof ResourceAccessException) {
            logger.warn("FastAPI connection failed: endpoint={}, exception={}",
                    endpoint, exception.getClass().getSimpleName());
            return new IllegalStateException("AI service is unreachable. Check its URL and try again.");
        }
        logger.warn("FastAPI request failed: endpoint={}, exception={}",
                endpoint, exception.getClass().getSimpleName());
        return new IllegalStateException("AI service request failed. Check backend logs for details.");
    }

    private boolean isTimeout(Throwable exception) {
        for (Throwable cause = exception; cause != null; cause = cause.getCause()) {
            if (cause instanceof SocketTimeoutException || cause instanceof HttpTimeoutException
                    || cause instanceof java.util.concurrent.TimeoutException) {
                return true;
            }
        }
        return false;
    }

    private String sanitizeForLog(String responseBody) {
        String sanitized = responseBody == null ? "" : responseBody;
        sanitized = BEARER_TOKEN.matcher(sanitized).replaceAll("$1[REDACTED]");
        sanitized = JWT_TOKEN.matcher(sanitized).replaceAll("[REDACTED_JWT]");
        sanitized = CREDENTIAL.matcher(sanitized).replaceAll("$1[REDACTED]");
        if (apiKey != null && !apiKey.isBlank()) {
            sanitized = sanitized.replace(apiKey, "[REDACTED]");
        }
        return sanitized.length() > 1000 ? sanitized.substring(0, 1000) + "…" : sanitized;
    }

    private String safeFastApiDetail(String responseBody) {
        try {
            JsonNode detail = objectMapper.readTree(responseBody).path("detail");
            if (detail.isTextual() && !detail.asText().isBlank()) {
                return detail.asText();
            }
            if (detail.isObject()) {
                String message = detail.path("message").asText("AI request failed");
                String reason = detail.path("reason").asText("");
                int failedRequirement = detail.path("failed_requirement").asInt(0);
                int totalRequirements = detail.path("total_requirements").asInt(0);
                if (failedRequirement > 0 && totalRequirements > 0) {
                    message += " at requirement " + failedRequirement + " of " + totalRequirements;
                }
                if (!reason.isBlank()) {
                    message += ": " + reason;
                }
                return message;
            }
        } catch (Exception ignored) {
            // Do not return raw upstream bodies, which could contain sensitive data.
        }
        return null;
    }
}
