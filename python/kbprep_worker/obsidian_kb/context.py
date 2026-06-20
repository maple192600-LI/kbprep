"""Template context for Obsidian knowledge-base rendering."""

from __future__ import annotations

from dataclasses import dataclass

from ..obsidian_template import ObsidianTemplate, load_obsidian_template


@dataclass(frozen=True)
class ObsidianContext:
    template_name: str
    template: ObsidianTemplate

    @property
    def categories(self) -> tuple[str, ...]:
        return self.template.categories

    @property
    def default_category(self) -> str:
        return self.template.default_category

    @property
    def method_category(self) -> str:
        return self.template.method_category

    @property
    def cognition_category(self) -> str:
        return self.template.cognition_category

    @property
    def case_category(self) -> str:
        return self.template.case_category

    @property
    def social_profile_labels(self) -> tuple[str, ...]:
        return self.template.social_profile_labels

    @property
    def social_profile_platforms(self) -> tuple[str, ...]:
        return self.template.social_profile_platforms

    @property
    def provenance_terms(self) -> tuple[str, ...]:
        return self.template.provenance_terms

    @property
    def author_bio_terms(self) -> tuple[str, ...]:
        return self.template.author_bio_terms

    @property
    def bio_role_terms(self) -> tuple[str, ...]:
        return self.template.bio_role_terms

    @property
    def author_credential_terms(self) -> tuple[str, ...]:
        return self.template.author_credential_terms

    @property
    def knowledge_terms(self) -> tuple[str, ...]:
        return self.template.knowledge_terms

    @property
    def case_terms(self) -> tuple[str, ...]:
        return self.template.case_terms

    @property
    def method_terms(self) -> tuple[str, ...]:
        return self.template.method_terms

    @property
    def cognition_terms(self) -> tuple[str, ...]:
        return self.template.cognition_terms

    @property
    def packaging_heading_terms(self) -> tuple[str, ...]:
        return self.template.packaging_heading_terms

    @property
    def packaging_heading_regexes(self) -> tuple[str, ...]:
        return self.template.packaging_heading_regexes

    @property
    def brand_heading_replacements(self) -> tuple[tuple[str, str], ...]:
        return self.template.brand_heading_replacements

    @property
    def layout_table_terms(self) -> tuple[str, ...]:
        return self.template.layout_table_terms

    @property
    def brand_program_packaging_terms(self) -> tuple[str, ...]:
        return self.template.brand_program_packaging_terms

    @property
    def translator_back_matter_terms(self) -> tuple[str, ...]:
        return self.template.translator_back_matter_terms


def context_for_template(template_name: str = "obsidian_generic") -> ObsidianContext:
    return ObsidianContext(template_name=template_name, template=load_obsidian_template(template_name))


def template_for_profile(profile: str = "obsidian_kb") -> str:
    if profile == "curated_obsidian_kb":
        return "obsidian_course_kb"
    return "obsidian_generic"
