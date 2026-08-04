"""Deterministic built-in Solution Catalogue; loading does not access a provider or repository."""

from __future__ import annotations

from forge.models import EngineeringEffort, RequiredDiscipline, SolutionTemplate, TemplateMissionCandidate


_BASE_DISCIPLINES = (RequiredDiscipline.BUSINESS, RequiredDiscipline.PLATFORM_ARCHITECTURE, RequiredDiscipline.ENGINEERING, RequiredDiscipline.UX, RequiredDiscipline.SECURITY, RequiredDiscipline.PRIVACY, RequiredDiscipline.COMPLIANCE)


def _template(identifier: str, name: str, purpose: str, capabilities: tuple[str, ...], candidates: tuple[tuple[str, str, str, str], ...]) -> SolutionTemplate:
    return SolutionTemplate(
        identifier, "1.0", name, purpose, ("end users", "business operators"), ("business owner", "platform architect"),
        ("deliver a governed, reusable product capability",), capabilities,
        tuple(TemplateMissionCandidate(key, title, objective, value, _BASE_DISCIPLINES, effort=EngineeringEffort.MEDIUM) for key, title, objective, value in candidates),
        ("modular service boundaries", "explicit integration contracts"), _BASE_DISCIPLINES,
        ("scope expansion", "integration assumptions", "security and privacy gaps"),
        ("assess applicable privacy, security, legal, and sector requirements",), ("discovery", "foundation", "capability delivery", "validation"),
    )


_BUILT_INS = (
    _template("web-application", "Web Application", "Deliver an accessible browser-based product.", ("identity", "responsive experience", "application workflows"), (("core-platform", "Core Platform", "Establish the application foundation.", "Enables governed delivery."), ("identity", "Identity", "Provide accountable access.", "Protects user and business data."))),
    _template("mobile-application", "Mobile Application", "Deliver a mobile-first product experience.", ("identity", "mobile experience", "offline capability"), (("core-platform", "Core Platform", "Establish mobile application foundations.", "Enables reliable mobile delivery."), ("offline-support", "Offline Support", "Assess and deliver offline needs.", "Supports resilient field use."))),
    _template("rest-api", "REST API", "Deliver a governed service integration surface.", ("API contracts", "identity", "observability"), (("api-foundation", "API Foundation", "Establish versioned API contracts.", "Enables safe integration."), ("integrations", "Integrations", "Connect declared external systems.", "Creates controlled interoperability."))),
    _template("crm", "CRM", "Manage customer relationships and service activity.", ("customer management", "reporting", "notifications"), (("core-platform", "Core Platform", "Establish CRM foundation.", "Enables customer operations."), ("identity", "Identity", "Provide role-aware access.", "Protects customer records."), ("customer-management", "Customer Management", "Manage customer data and interactions.", "Improves customer service."), ("reporting", "Reporting", "Provide accountable business insight.", "Supports decisions."), ("notifications", "Notifications", "Deliver governed communications.", "Improves responsiveness."), ("integrations", "Integrations", "Connect declared business systems.", "Reduces manual work."))),
    _template("erp", "ERP", "Coordinate core enterprise resource workflows.", ("workflow management", "reporting", "integrations"), (("core-platform", "Core Platform", "Establish ERP foundation.", "Enables business operations."), ("workflow-management", "Workflow Management", "Define controlled operational workflows.", "Improves consistency."), ("integrations", "Integrations", "Connect declared enterprise systems.", "Reduces duplication."))),
    _template("dashboard", "Dashboard", "Present governed operational insight.", ("reporting", "data visualisation", "identity"), (("data-foundation", "Data Foundation", "Establish accountable data inputs.", "Supports trustworthy insight."), ("reporting", "Reporting", "Present decision-ready information.", "Improves visibility."))),
    _template("knowledge-base", "Knowledge Base", "Publish and maintain searchable organisational knowledge.", ("content management", "search", "identity"), (("content-foundation", "Content Foundation", "Establish governed knowledge structure.", "Improves findability."), ("search", "Search", "Deliver relevant knowledge retrieval.", "Reduces support effort."))),
    _template("ai-assistant", "AI Assistant", "Assist users through a governed conversational experience.", ("conversation experience", "knowledge access", "safety controls"), (("assistant-foundation", "Assistant Foundation", "Establish safe assistant boundaries.", "Enables accountable assistance."), ("knowledge-integration", "Knowledge Integration", "Connect approved knowledge sources.", "Improves answer quality."))),
    _template("iot-platform", "IoT Platform", "Coordinate connected-device capabilities.", ("device management", "telemetry", "identity"), (("device-foundation", "Device Foundation", "Establish device identity and lifecycle.", "Enables safe operations."), ("telemetry", "Telemetry", "Provide accountable device insight.", "Improves reliability."))),
    _template("media-platform", "Media Platform", "Deliver governed media discovery and delivery.", ("catalogue", "delivery", "identity"), (("catalogue", "Content Catalogue", "Establish governed media metadata.", "Improves discovery."), ("delivery", "Media Delivery", "Provide reliable media delivery.", "Improves user experience."))),
    _template("e-commerce", "E-commerce", "Enable governed digital commerce.", ("catalogue", "checkout", "order management"), (("storefront", "Storefront", "Establish accessible shopping experience.", "Enables sales."), ("checkout", "Checkout", "Deliver secure purchase workflows.", "Protects customers and revenue."), ("order-management", "Order Management", "Manage fulfilment visibility.", "Improves operations."))),
    _template("internal-tool", "Internal Tool", "Improve a controlled internal business workflow.", ("workflow management", "identity", "reporting"), (("workflow-foundation", "Workflow Foundation", "Establish accountable internal workflows.", "Reduces manual effort."), ("reporting", "Reporting", "Provide operational visibility.", "Improves management."))),
    _template("automation-platform", "Automation Platform", "Coordinate reusable business automation.", ("workflow orchestration", "integrations", "observability"), (("automation-foundation", "Automation Foundation", "Establish controlled automation boundaries.", "Enables safe automation."), ("integrations", "Integrations", "Connect approved systems.", "Reduces manual handoffs."))),
)


class SolutionCatalogue:
    """Immutable template registry. Extra templates can be supplied without changing built-ins."""

    def __init__(self, templates: tuple[SolutionTemplate, ...] = _BUILT_INS) -> None:
        if len(templates) != len({(item.identifier, item.version) for item in templates}):
            raise ValueError("solution catalogue template identity and version must be unique")
        self._templates = tuple(sorted(templates, key=lambda item: (item.identifier, item.version)))

    def list(self) -> tuple[SolutionTemplate, ...]:
        return self._templates

    def get(self, identifier: str, version: str = "1.0") -> SolutionTemplate:
        for template in self._templates:
            if (template.identifier, template.version) == (identifier, version):
                return template
        raise KeyError(f"unknown solution template: {identifier}@{version}")
