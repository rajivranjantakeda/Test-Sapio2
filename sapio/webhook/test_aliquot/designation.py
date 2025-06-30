import re
from typing import List

from sapiopylib.rest.pojo.eln.ElnExperiment import ElnTemplate, TemplateExperimentQueryPojo
from sapiopylib.rest.pojo.webhook.WebhookContext import SapioWebhookContext

from sapio.enum.tags import TemplateDescriptionTags


class DesignationManager:
    """
    A class for finding templates based on the designation tag in the description. Ensures case insensitivity
    and caches templates for efficiency.
    """
    initialized = False
    templates_by_designation: dict[str, ElnTemplate] = dict()
    context: SapioWebhookContext = None
    designation_tag_regex: re.Pattern = None

    def __init__(self, context: SapioWebhookContext):
        self.context = context
        if not self.initialized:
            # Initialize class variables when initializing the first instance.
            self.initialized = True
            self.designation_tag_regex = re.compile(TemplateDescriptionTags.TEMPLATE_DESIGNATION)
            self.__load_designations()

    def __load_designations(self):
        """ Loads all the templates and their designations into the cache. Requires one webservice query to execute."""
        # Get all the templates in the system.
        query = TemplateExperimentQueryPojo(active_templates_only=False)
        templates: List[ElnTemplate] = self.context.eln_manager.get_template_experiment_list(query)

        # Iterate over every single one, and check to see if it's description attribute matches our tag regex.
        self.templates_by_designation = dict()
        for template in templates:
            designation = self.get_template_designation(template)
            if designation is None:
                continue
            # We have a match to a designation, so store the template.
            self.templates_by_designation[designation] = template

    def get_template_designation(self, template: ElnTemplate):
        """ Given an eln template, parse out the designation from the designation tag in the description."""
        matches = self.designation_tag_regex.findall(template.description)
        return matches[0] if matches else None

    def __add_designation_template(self, designation: str, template: ElnTemplate):
        """ Sets the designation to template mapping. The mapping is case-insensitive."""
        self.templates_by_designation[designation.upper()] = template

    def get_template(self, designation: str) -> ElnTemplate | None:
        """ Gets the template associated with the given designation. The designation is case-insensitive."""
        return self.templates_by_designation.get(designation.upper())

    def get_designation(self, template_id: int | None) -> str | None:
        """ Gets the template based on the template id and parses out the designation from the description. This
        requires one webservice call to execute."""
        if template_id is None:
            return None

        # Iterate over the templates that we have in our cache. When we find one that matches, parse out the
        # designation. and return it.
        for template in self.templates_by_designation.values():
            if template.template_id == template_id:
                return self.get_template_designation(template)

        # None found. return None.
        return None
