"""Regression coverage for deterministic Capability Delegation."""

import unittest

from forge.capabilities import (CapabilityAvailability, CapabilityExecutionMode, CapabilityOwner,
                                CapabilityRegistration, CapabilityRegistry)


class CapabilityDelegationTests(unittest.TestCase):
    def test_registry_assessment_is_deterministic_for_internal_and_external_capabilities(self) -> None:
        registry = CapabilityRegistry((
            CapabilityRegistration("internal", "Internal", CapabilityOwner.FORGE, CapabilityAvailability.AVAILABLE,
                                   CapabilityExecutionMode.INTERNAL, CapabilityOwner.FORGE, "trusted"),
            CapabilityRegistration("external", "External", CapabilityOwner.HUMAN, CapabilityAvailability.UNAVAILABLE,
                                   CapabilityExecutionMode.DELEGATED, CapabilityOwner.HUMAN, "reviewed", True),
        ))
        internal = registry.assess("internal")
        external = registry.assess("external")
        self.assertTrue(internal.available)
        self.assertEqual(internal.selected_provider, CapabilityOwner.FORGE)
        self.assertFalse(external.available)
        self.assertEqual(external.selected_provider, CapabilityOwner.HUMAN)
        self.assertTrue(external.approval_required)
        self.assertEqual(external.to_dict(), registry.assess("external").to_dict())

    def test_unregistered_capability_fails_closed(self) -> None:
        registry = CapabilityRegistry((CapabilityRegistration("known", "Known", CapabilityOwner.FORGE,
                                                               CapabilityAvailability.AVAILABLE, CapabilityExecutionMode.INTERNAL,
                                                               CapabilityOwner.FORGE, "trusted"),))
        with self.assertRaisesRegex(ValueError, "not registered"):
            registry.assess("unknown")
