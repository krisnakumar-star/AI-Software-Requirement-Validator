package com.reqvalidator.backend.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;

class RequirementExtractionServiceTest {

    private final RequirementExtractionService service = new RequirementExtractionService();

    @Test
    void preservesIdsSectionsAndWrappedLines() {
        String text = """
                1. Introduction
                This document describes the system.
                3.1 Functional Requirements
                FR-1: The system shall allow users to register with an email
                address and password.
                FR-2: Users shall be able to log in.
                REQ-010 The system shall send a confirmation email.
                """;
        var result = service.extract(text);
        List<RequirementExtractionService.ExtractedRequirement> reqs = result.requirements();
        assertEquals(3, reqs.size());
        assertEquals("FR-1", reqs.get(0).sourceId());
        assertEquals("The system shall allow users to register with an email address and password.", reqs.get(0).text());
        assertEquals("3.1 Functional Requirements", reqs.get(0).section());
        assertEquals("REQ-010", reqs.get(2).sourceId());
    }

    @Test
    void reportsDuplicatesAndHandlesBullets() {
        String text = """
                Requirements
                • User login / signup
                • Product browsing and search
                - The system shall export reports.
                - The system shall export reports.
                """;
        var result = service.extract(text);
        assertEquals(3, result.requirements().size());
        assertEquals(1, result.duplicatesSkipped());
        assertTrue(result.warnings().get(0).contains("duplicate"));
    }

    @Test
    void emptyTextYieldsNothing() {
        assertTrue(service.extract("   ").requirements().isEmpty());
        assertTrue(service.extract(null).requirements().isEmpty());
    }
}
