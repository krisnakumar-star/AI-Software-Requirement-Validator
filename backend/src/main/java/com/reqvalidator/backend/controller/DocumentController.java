package com.reqvalidator.backend.controller;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.extractor.WordExtractor;
import org.apache.poi.xwpf.extractor.XWPFWordExtractor;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.reqvalidator.backend.model.Document;
import com.reqvalidator.backend.model.Project;
import com.reqvalidator.backend.model.Requirement;
import com.reqvalidator.backend.repository.DocumentRepository;
import com.reqvalidator.backend.repository.ProjectRepository;
import com.reqvalidator.backend.repository.RequirementRepository;

@RestController
@RequestMapping("/api/documents")
@CrossOrigin(origins = {"http://localhost:5173", "https://ai-software-requirement-validator.vercel.app"})
public class DocumentController {

    private final RequirementRepository requirementRepository;
    private final DocumentRepository documentRepository;
    private final ProjectRepository projectRepository;
    private final com.reqvalidator.backend.service.RequirementExtractionService extractionService;

    public DocumentController(
            RequirementRepository requirementRepository,
            DocumentRepository documentRepository,
            ProjectRepository projectRepository,
            com.reqvalidator.backend.service.RequirementExtractionService extractionService) {
        this.extractionService = extractionService;

        this.requirementRepository = requirementRepository;
        this.documentRepository = documentRepository;
        this.projectRepository = projectRepository;
    }

    // =========================================================
    // UPLOAD DOCUMENT
    // =========================================================

    @PostMapping("/upload")
    public ResponseEntity<?> uploadDocument(
            @RequestParam("file") MultipartFile file,
            @RequestParam("projectId") String projectId) {

        try {

            // -------------------------------------------------
            // 1. Check empty file
            // -------------------------------------------------

            if (file.isEmpty()) {
                return ResponseEntity
                        .badRequest()
                        .body("Please select a file.");
            }

            // -------------------------------------------------
            // 2. Check project exists
            // -------------------------------------------------

            Project project = projectRepository
                    .findById(projectId)
                    .orElse(null);

            if (project == null) {
                return ResponseEntity
                        .status(HttpStatus.NOT_FOUND)
                        .body("Project not found.");
            }

            // -------------------------------------------------
            // 3. Check authenticated user
            // -------------------------------------------------

            String authenticatedEmail =
                    SecurityContextHolder
                            .getContext()
                            .getAuthentication()
                            .getName();

            // -------------------------------------------------
            // 4. Check project ownership
            // -------------------------------------------------

            if (!authenticatedEmail.equalsIgnoreCase(
                    project.getOwnerEmail())) {

                return ResponseEntity
                        .status(HttpStatus.FORBIDDEN)
                        .body(
                                "You are not allowed to upload documents to this project."
                        );
            }

            // -------------------------------------------------
            // 5. Get and validate file name
            // -------------------------------------------------

            String originalFileName =
                    file.getOriginalFilename();

            if (originalFileName == null
                    || originalFileName.trim().isEmpty()) {

                return ResponseEntity
                        .badRequest()
                        .body("Invalid file name.");
            }

            String fileName =
                    new File(originalFileName).getName();

            // -------------------------------------------------
            // 6. Check duplicate document
            // -------------------------------------------------

            if (documentRepository
                    .findByProjectIdAndFileName(
                            projectId,
                            fileName
                    )
                    .isPresent()) {

                return ResponseEntity
                        .badRequest()
                        .body(
                                "Document already uploaded for this project: "
                                        + fileName
                        );
            }

            // -------------------------------------------------
            // 7. Get file extension
            // -------------------------------------------------

            String extension = "";

            int lastDot =
                    fileName.lastIndexOf(".");

            if (lastDot != -1) {
                extension =
                        fileName.substring(
                                lastDot + 1
                        ).toLowerCase();
            }

            // -------------------------------------------------
            // 8. Check supported file types
            // -------------------------------------------------

            if (!extension.equals("pdf")
                    && !extension.equals("doc")
                    && !extension.equals("docx")
                    && !extension.equals("txt")) {

                return ResponseEntity
                        .badRequest()
                        .body(
                                "Unsupported file type. "
                                        + "Only PDF, DOC, DOCX and TXT files are allowed."
                        );
            }

            // -------------------------------------------------
            // 9. Save physical file
            // -------------------------------------------------

            File uploadDirectory =
                    new File("uploads");

            if (!uploadDirectory.exists()) {
                uploadDirectory.mkdirs();
            }

            File savedFile =
                    new File(
                            uploadDirectory,
                            fileName
                    );

            try (
                    FileOutputStream outputStream =
                            new FileOutputStream(savedFile)
            ) {

                outputStream.write(
                        file.getBytes()
                );
            }

            // -------------------------------------------------
            // 10. Extract text
            // -------------------------------------------------

            String extractedText;

            try {
            if (extension.equals("pdf")) {

                extractedText =
                        extractTextFromPdf(
                                file.getBytes()
                        );

            } else if (extension.equals("docx")) {

                extractedText =
                        extractTextFromDocx(
                                file.getBytes()
                        );

            } else if (extension.equals("doc")) {

                extractedText =
                        extractTextFromDoc(
                                file.getBytes()
                        );

            } else {

                extractedText =
                        new String(
                                file.getBytes(),
                                StandardCharsets.UTF_8
                        );
            }
            } catch (IOException | RuntimeException extractionError) {
                return ResponseEntity
                        .badRequest()
                        .body("The document could not be read. It may be corrupted, password-protected, or not a valid "
                                + extension.toUpperCase() + " file.");
            }

            if (extractedText == null || extractedText.isBlank()) {
                return ResponseEntity
                        .badRequest()
                        .body("No readable text was found in the document. Scanned or image-only PDFs are not supported.");
            }

            // -------------------------------------------------
            // 11. Extract requirements
            // -------------------------------------------------

            com.reqvalidator.backend.service.RequirementExtractionService.ExtractionResult extraction =
                    extractionService.extract(extractedText);
            var extractedRequirements = extraction.requirements();

            if (extractedRequirements.isEmpty()) {
                return ResponseEntity
                        .badRequest()
                        .body("No requirements were detected. Requirements should contain 'shall', 'must', 'should' or 'will', "
                                + "or be listed as bullets/IDs under a 'Requirements' heading.");
            }

            // -------------------------------------------------
            // 12. Save document metadata
            // -------------------------------------------------

            Document document =
                    new Document();

            document.setProjectId(
                    projectId
            );

            document.setFileName(
                    fileName
            );

            document.setFileType(
                    extension
            );

            document.setFileSize(
                    file.getSize()
            );

            document.setUploadTime(
                    LocalDateTime.now().toString()
            );

            documentRepository.save(
                    document
            );

            // -------------------------------------------------
            // 13. Generate requirement IDs
            // -------------------------------------------------

            long existingCount =
                    requirementRepository
                            .countByProjectId(
                                    projectId
                            );

            int requirementNumber =
                    (int) existingCount + 1;

            int savedCount = 0;

            // -------------------------------------------------
            // 14. Save extracted requirements
            // -------------------------------------------------

            java.util.Set<String> usedIds = new java.util.HashSet<>();
            requirementRepository.findByProjectId(projectId)
                    .forEach(existing -> usedIds.add(String.valueOf(existing.getRequirementId())));

            for (var extracted :
                    extractedRequirements) {

                String requirementText = extracted.text();

                Requirement requirement =
                        new Requirement();

                requirement.setProjectId(
                        projectId
                );

                String requirementId = extracted.sourceId();
                if (requirementId == null || usedIds.contains(requirementId)) {
                    do {
                        requirementId = String.format("REQ-%03d", requirementNumber++);
                    } while (usedIds.contains(requirementId));
                }
                usedIds.add(requirementId);
                requirement.setRequirementId(requirementId);
                requirement.setSourceSection(extracted.section());
                requirement.setSourceDocument(fileName);

                requirement.setRequirementText(
                        requirementText
                );

                // Validation fields
                requirement.setClarity("");
                requirement.setAmbiguity("");
                requirement.setCompleteness("");
                requirement.setConsistency("");
                requirement.setConsistencyWith(null);
                requirement.setConsistencyReason(null);
                requirement.setTestability("");
                requirement.setMeasurability("");

                // Duplicate fields
                requirement.setDuplicateStatus("");
                requirement.setDuplicateSimilarity(null);
                requirement.setDuplicateWith(null);

                // Issues
                requirement.setIssues(
                        new ArrayList<>()
                );

                // Suggestions
                requirement.setSuggestions(
                        new ArrayList<>()
                );

                // Score and status
                requirement.setQualityScore(null);
                requirement.setStatus("Pending");

                requirementRepository.save(
                        requirement
                );

                savedCount++;
            }

            // -------------------------------------------------
            // 15. Return response
            // -------------------------------------------------

            String response =
                    "File uploaded successfully: "
                            + fileName
                            + "\n\n"
                            + "File type: "
                            + extension
                            + "\n"
                            + "File size: "
                            + file.getSize()
                            + " bytes\n"
                            + "Upload time: "
                            + document.getUploadTime()
                            + "\n\n"
                            + "Requirements extracted: "
                            + savedCount
                            + (extraction.warnings().isEmpty() ? "" : "\nNotes: " + String.join(" ", extraction.warnings()))
                            + "\n\n"
                            + "Extracted Text:\n\n"
                            + (extractedText.length() > 20000 ? extractedText.substring(0, 20000) + "\n[truncated]" : extractedText);

            return ResponseEntity.ok(
                    response
            );

        } catch (IOException e) {

            throw new RuntimeException(
                    "Error processing uploaded document.",
                    e
            );
        }
    }

    // =========================================================
    // GET DOCUMENTS BY PROJECT
    // =========================================================

    @GetMapping("/project/{projectId}")
    public ResponseEntity<?> getDocumentsByProject(
            @PathVariable String projectId) {

        String authenticatedEmail =
                SecurityContextHolder
                        .getContext()
                        .getAuthentication()
                        .getName();

        Project project =
                projectRepository
                        .findById(projectId)
                        .orElse(null);

        if (project == null) {

            return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .body("Project not found.");
        }

        if (!authenticatedEmail.equalsIgnoreCase(
                project.getOwnerEmail())) {

            return ResponseEntity
                    .status(HttpStatus.FORBIDDEN)
                    .body(
                            "You are not allowed to access this project's documents."
                    );
        }

        return ResponseEntity.ok(
                documentRepository.findByProjectId(
                        projectId
                )
        );
    }

    // =========================================================
    // PDF TEXT EXTRACTION
    // =========================================================

    private String extractTextFromPdf(
            byte[] fileBytes) throws IOException {

        try (
                PDDocument document =
                        Loader.loadPDF(fileBytes)
        ) {

            PDFTextStripper stripper =
                    new PDFTextStripper();

            return stripper.getText(
                    document
            );
        }
    }

    // =========================================================
    // DOCX TEXT EXTRACTION
    // =========================================================

    private String extractTextFromDocx(
            byte[] fileBytes) throws IOException {

        try (
                XWPFDocument document =
                        new XWPFDocument(
                                new ByteArrayInputStream(
                                        fileBytes
                                )
                        );

                XWPFWordExtractor extractor =
                        new XWPFWordExtractor(
                                document
                        )
        ) {

            return extractor.getText();
        }
    }

    // =========================================================
    // DOC TEXT EXTRACTION
    // =========================================================

    private String extractTextFromDoc(
            byte[] fileBytes) throws IOException {

        try (
                HWPFDocument document =
                        new HWPFDocument(
                                new ByteArrayInputStream(
                                        fileBytes
                                )
                        );

                WordExtractor extractor =
                        new WordExtractor(
                                document
                        )
        ) {

            return extractor.getText();
        }
    }

    // =========================================================
    // REQUIREMENT EXTRACTION
    // =========================================================

    private List<String> extractRequirements(
            String text) {

        List<String> requirements =
                new ArrayList<>();

        if (text == null
                || text.trim().isEmpty()) {

            return requirements;
        }

        String[] lines =
                text.split("\\r?\\n");

        boolean insideRequirementsSection = false;

        for (String line : lines) {

            String trimmedLine =
                    line.trim();

            if (trimmedLine.isEmpty()) {
                continue;
            }

            // -------------------------------------------------
            // Remove common bullet characters temporarily
            // -------------------------------------------------

            String cleanedLine =
                    trimmedLine.replaceFirst(
                            "^[•\\-–—*]\\s+",
                            ""
                    ).trim();

            // -------------------------------------------------
            // Remove existing requirement ID
            //
            // Example:
            // REQ-001: The system shall allow users.
            //
            // Becomes:
            // The system shall allow users.
            // -------------------------------------------------

            cleanedLine =
                    cleanedLine.replaceFirst(
                            "(?i)^REQ-\\d+\\s*:\\s*",
                            ""
                    ).trim();

            if (cleanedLine.isEmpty()) {
                continue;
            }

            String lowerCase =
                    cleanedLine.toLowerCase();

            // -------------------------------------------------
            // Detect Requirements section
            // -------------------------------------------------

            if (lowerCase.matches(
                    "^\\d+\\.?\\s*requirements\\s*$")
                    || lowerCase.matches(
                    "^requirements\\s*$")
                    || lowerCase.matches(
                    "^\\d+\\.?\\s*functional requirements\\s*$")) {

                insideRequirementsSection = true;
                continue;
            }

            // -------------------------------------------------
            // Stop at common major sections
            // -------------------------------------------------

            if (insideRequirementsSection
                    && lowerCase.matches(
                    "^\\d+\\.?\\s*(analysis|design|implementation|conclusion|references).*$")) {

                insideRequirementsSection = false;
            }

            // -------------------------------------------------
            // Formal SRS requirements
            // -------------------------------------------------

            if (lowerCase.matches(
                    ".*\\bshall\\b.*")
                    || lowerCase.matches(
                    ".*\\bshould\\b.*")
                    || lowerCase.matches(
                    ".*\\bmust\\b.*")) {

                if (cleanedLine.length() >= 10) {

                    requirements.add(
                            cleanedLine
                    );
                }

                continue;
            }

            // -------------------------------------------------
            // Bullet-style requirements
            //
            // Example:
            // • User login / signup
            // • Product browsing
            // • Search and filter
            // -------------------------------------------------

            if (insideRequirementsSection
                    && trimmedLine.matches(
                    "^[•\\-–—*]\\s+.+")) {

                if (cleanedLine.length() >= 8) {

                    requirements.add(
                            cleanedLine
                    );
                }
            }
        }

        // -------------------------------------------------
        // Remove duplicate requirements
        // while preserving original order
        // -------------------------------------------------

        List<String> uniqueRequirements =
                new ArrayList<>();

        for (String requirement :
                requirements) {

            boolean alreadyExists = false;

            for (String existing :
                    uniqueRequirements) {

                if (existing.equalsIgnoreCase(
                        requirement)) {

                    alreadyExists = true;
                    break;
                }
            }

            if (!alreadyExists) {

                uniqueRequirements.add(
                        requirement
                );
            }
        }

        return uniqueRequirements;
    }
}