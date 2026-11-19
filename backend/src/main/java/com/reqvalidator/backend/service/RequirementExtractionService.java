package com.reqvalidator.backend.service;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.stereotype.Service;

/**
 * Extracts requirement statements from plain document text.
 *
 * Preserves source requirement IDs (REQ-001, FR-1, NFR-2.1, 3.2.1) and the
 * current section heading, joins lines wrapped by PDF/Word extraction, and
 * reports exact duplicates instead of silently discarding them.
 */
@Service
public class RequirementExtractionService {

    public static final int MAX_REQUIREMENTS = 1000;

    private static final Pattern ID_PREFIX = Pattern.compile(
            "^[\\[(]?((?:[A-Z][A-Z0-9]{0,9}[-_ .]?\\d+(?:[.\\-]\\d+)*)|(?:\\d+(?:\\.\\d+){1,4}))[\\])]?\\s*(?:[:\\-–—.)]\\s*|\\s+(?=[A-Z]))(.+)$");
    private static final Pattern BULLET = Pattern.compile("^(?:[•\\-–—*▪◦·]|\\(?[a-z0-9]{1,3}[.)])\\s+(.+)$");
    private static final Pattern MODAL = Pattern.compile(
            "\\b(shall|must|should|will|is required to|are required to|needs to|has to)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern USER_STORY = Pattern.compile("^as an?\\s+.+\\bi\\s+(want|need|would like)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern HEADING = Pattern.compile("^((?:\\d+\\.)*\\d+\\.?)\\s+([A-Z][^.:;]{2,80})$");
    private static final Pattern REQUIREMENTS_HEADING = Pattern.compile(
            "^(?:\\d+(?:\\.\\d+)*\\.?\\s*)?((functional|non[- ]functional|system|software|user|business|performance|security|quality)\\s+)?requirements?\\s*$",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern END_SECTION = Pattern.compile(
            "^(?:\\d+(?:\\.\\d+)*\\.?\\s*)?(analysis|design|implementation|conclusion|references|appendix|glossary|bibliography)\\b.*$",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern PROSE = Pattern.compile(
            "^(this (document|section|chapter|srs)|the purpose of|in this (document|section)|the following (section|chapter))",
            Pattern.CASE_INSENSITIVE);

    public record ExtractedRequirement(String sourceId, String text, String section) {
    }

    public record ExtractionResult(List<ExtractedRequirement> requirements, int duplicatesSkipped,
                                   boolean truncated, List<String> warnings) {
    }

    public ExtractionResult extract(String text) {
        List<ExtractedRequirement> found = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        if (text == null || text.isBlank()) {
            return new ExtractionResult(found, 0, false, warnings);
        }

        String section = null;
        boolean inRequirementsSection = false;
        Candidate current = null;
        List<Candidate> candidates = new ArrayList<>();

        for (String rawLine : text.replace("﻿", "").split("\\r?\\n")) {
            String line = rawLine.replace(' ', ' ').trim().replaceAll("\\s+", " ");
            if (line.isEmpty()) {
                current = close(current, candidates);
                continue;
            }
            if (REQUIREMENTS_HEADING.matcher(line).matches()) {
                current = close(current, candidates);
                inRequirementsSection = true;
                section = line;
                continue;
            }
            if (END_SECTION.matcher(line).matches() && line.length() < 80) {
                current = close(current, candidates);
                inRequirementsSection = false;
                section = line;
                continue;
            }
            Matcher heading = HEADING.matcher(line);
            if (heading.matches() && !MODAL.matcher(line).find()) {
                current = close(current, candidates);
                section = line;
                continue;
            }

            String sourceId = null;
            String body = line;
            boolean bullet = false;
            Matcher id = ID_PREFIX.matcher(line);
            if (id.matches() && id.group(2).length() >= 8) {
                sourceId = id.group(1).trim().replace(' ', '-');
                body = id.group(2).trim();
            } else {
                Matcher b = BULLET.matcher(line);
                if (b.matches()) {
                    body = b.group(1).trim();
                    bullet = true;
                }
            }

            boolean statement = MODAL.matcher(body).find() || USER_STORY.matcher(body).find();
            boolean starts = sourceId != null || bullet || statement;

            // Continuation of a wrapped line: previous candidate has no terminal punctuation,
            // and this line is not a new ID/bullet and starts in lower case or continues a clause.
            if (current != null && sourceId == null && !bullet
                    && !current.text.toString().matches(".*[.!?;]$")
                    && (Character.isLowerCase(body.charAt(0)) || !statement)) {
                current.text.append(' ').append(body);
                continue;
            }
            current = close(current, candidates);
            if (!starts || PROSE.matcher(body).find()) {
                continue;
            }
            if (!statement && !(inRequirementsSection && (bullet || sourceId != null))) {
                continue;
            }
            current = new Candidate(sourceId, body, section);
        }
        close(current, candidates);

        Set<String> seen = new LinkedHashSet<>();
        int duplicates = 0;
        boolean truncated = false;
        for (Candidate candidate : candidates) {
            String requirement = candidate.text.toString().trim();
            if (requirement.length() < 8) {
                continue;
            }
            String key = requirement.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", " ").trim();
            if (!seen.add(key)) {
                duplicates++;
                continue;
            }
            if (found.size() >= MAX_REQUIREMENTS) {
                truncated = true;
                break;
            }
            found.add(new ExtractedRequirement(candidate.sourceId, requirement, candidate.section));
        }
        if (duplicates > 0) {
            warnings.add(duplicates + " exact duplicate statement(s) were skipped.");
        }
        if (truncated) {
            warnings.add("Only the first " + MAX_REQUIREMENTS + " requirements were imported.");
        }
        return new ExtractionResult(found, duplicates, truncated, warnings);
    }

    private Candidate close(Candidate current, List<Candidate> candidates) {
        if (current != null) {
            candidates.add(current);
        }
        return null;
    }

    private static final class Candidate {
        final String sourceId;
        final StringBuilder text;
        final String section;

        Candidate(String sourceId, String text, String section) {
            this.sourceId = sourceId;
            this.text = new StringBuilder(text);
            this.section = section;
        }
    }
}
