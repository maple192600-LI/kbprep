"""Quality gate thresholds."""

DIAGNOSIS_THRESHOLDS = {
    "replacement_char_low_signal_ratio": 0.2,
    "pdf_unreadable_text_layer": 0.25,
    "pdf_mojibake_strict": 0.08,
    "pdf_garbled_strict": 0.08,
    "pdf_mojibake_warn": 0.03,
    "pdf_garbled_warn": 0.03,
    "post_convert_pdf_text_layer_unreadable": 0.08,
    "pdf_image_page_ratio": 0.5,
    "pdf_large_page_count": 80,
    "pdf_large_sample_head_pages": 5,
    "pdf_large_sample_tail_pages": 5,
    "pdf_large_sample_stride": 10,
    "pdf_landscape_ratio": 0.8,
    "pdf_multi_column_min_blocks": 4,
    "pdf_slide_image_score": 0.25,
    "pdf_slide_text_score": 0.2,
    "pdf_slide_like_score": 0.65,
    "markdown_garbled_warn": 0.05,
}

CLASSIFICATION_CONFIDENCE = {
    "marketing_wrapper_discard": 0.96,
    "structural_keep": 0.90,
    "image_unclassified": 0.0,
    "protected_keep": 0.90,
    "contextual_cta_keep": 0.88,
    "discard_pattern": 0.95,
    "evidence_pattern": 0.85,
    "garbled_discard": 0.80,
    "default_keep": 0.70,
}

OBSIDIAN_CONFIDENCE = {
    "keep_html_diagram": 0.92,
    "drop_image_artifact": 0.94,
    "drop_internal_page_marker": 0.99,
    "drop_slide_chapter_divider": 0.94,
    "drop_layout_separator": 0.95,
    "drop_translator_back_matter": 0.94,
    "drop_author_profile_links": 0.92,
    "drop_author_identity_card": 0.91,
    "drop_layout_table": 0.86,
    "drop_packaging_context": 0.88,
    "drop_brand_program_packaging": 0.87,
    "drop_empty_heading": 0.92,
    "drop_packaging_heading": 0.90,
    "author_intro_review": 0.60,
    "drop_author_intro": 0.90,
    "drop_toc": 0.90,
    "drop_toc_heading": 0.88,
}

REVIEW_THRESHOLDS = {
    "review_pack_low_confidence": 0.76,
}

CONVERSION_THRESHOLDS = {
    "garbage_ratio_warn": 0.03,
    "garbage_ratio_strict": 0.08,
    "empty_page_ratio_warn": 0.05,
    "missing_image_file_strict": 1,
    "structure_loss_strict": 0,
}

CLEANING_THRESHOLDS = {
    "protected_block_loss_strict": 0,
    "operation_step_loss_strict": 0,
    "prompt_loss_strict": 0,
    "code_block_loss_strict": 0,
    "table_loss_strict": 0,
    "qr_image_in_cleaned_strict": 0,
    "cta_in_cleaned_strict": 0,
    "discard_ratio_warn": 0.25,
    "discard_ratio_strict": 0.45,
}

SPLITTING_THRESHOLDS = {
    "chunk_chars_min_warn": 300,
    "chunk_chars_max_warn": 3500,
    "broken_ordered_list_strict": 0,
    "broken_code_block_strict": 0,
    "broken_table_strict": 0,
    "missing_block_trace_strict": 0,
}

COVERAGE_THRESHOLDS = {
    "warn": {
        "pdf_like": 0.82,
        "markdown_note": 0.86,
        "generic_block": 0.88,
    },
    "strict": {
        "pdf_like": 0.72,
        "markdown_note": 0.76,
        "generic_block": 0.78,
    },
}

