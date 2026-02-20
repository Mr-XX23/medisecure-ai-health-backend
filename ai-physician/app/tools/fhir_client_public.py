"""Enhanced FHIR client with support for public FHIR test servers.

This module can connect to:
- Public FHIR test servers (HAPI FHIR, SMART Health IT)
- Mock data for development
- Real EHR systems (Epic, Cerner, etc.)
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import httpx
import os

logger = logging.getLogger(__name__)

# Load FHIR settings from environment variables directly
# This avoids requiring all Settings() parameters
fhir_use_mock = os.getenv("FHIR_USE_MOCK", "true").lower() == "true"
fhir_enabled = os.getenv("FHIR_ENABLED", "false").lower() == "true"
fhir_base_url = os.getenv("FHIR_BASE_URL", "http://hapi.fhir.org/baseR4")
fhir_auth_token = os.getenv("FHIR_AUTH_TOKEN")


class FHIRClient:
    """FHIR client that can use real servers or mock data."""

    def __init__(self, use_mock: Optional[bool] = None, base_url: Optional[str] = None):
        """
        Initialize FHIR client.

        Args:
            use_mock: Force mock mode (overrides settings)
            base_url: FHIR server base URL (overrides settings)
        """
        self.use_mock = (
            use_mock if use_mock is not None else fhir_use_mock or not fhir_enabled
        )
        self.base_url = base_url or fhir_base_url
        self.auth_token = fhir_auth_token
        self.timeout = 10.0  # seconds

        logger.info(
            f"FHIR Client initialized - Mode: {'MOCK' if self.use_mock else 'REAL'}, "
            f"Server: {self.base_url if not self.use_mock else 'N/A'}"
        )

    async def _make_request(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> Optional[Dict]:
        """
        Make HTTP request to FHIR server.

        Args:
            resource_type: FHIR resource type (Patient, Condition, etc.)
            resource_id: Specific resource ID
            params: Query parameters

        Returns:
            FHIR resource or Bundle
        """
        try:
            # Build URL
            url = f"{self.base_url}/{resource_type}"
            if resource_id:
                url = f"{url}/{resource_id}"

            # Build headers
            headers = {
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            }
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            # Make request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.warning(f"FHIR request timeout for {resource_type}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"FHIR request failed: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"FHIR request error: {str(e)}")
            return None

    def _parse_fhir_patient(self, fhir_patient: Dict) -> Optional[Dict]:
        """Parse FHIR Patient resource to simplified format."""
        try:
            # Extract birth date
            birth_date_str = fhir_patient.get("birthDate", "")
            birth_date = (
                datetime.strptime(birth_date_str, "%Y-%m-%d")
                if birth_date_str
                else None
            )
            age = (datetime.now() - birth_date).days // 365 if birth_date else None

            # Extract name
            names = fhir_patient.get("name", [])
            full_name = "Unknown"
            if names:
                given = " ".join(names[0].get("given", []))
                family = names[0].get("family", "")
                full_name = f"{given} {family}".strip()

            return {
                "id": fhir_patient.get("id"),
                "name": full_name,
                "date_of_birth": birth_date_str,
                "gender": fhir_patient.get("gender", "unknown"),
                "age": age,
            }
        except Exception as e:
            logger.error(f"Error parsing FHIR patient: {str(e)}")
            return None

    def _parse_fhir_conditions(self, fhir_bundle: Dict) -> List[Dict]:
        """Parse FHIR Condition Bundle to simplified format."""
        conditions = []
        try:
            entries = fhir_bundle.get("entry", [])
            for entry in entries:
                resource = entry.get("resource", {})
                if resource.get("resourceType") != "Condition":
                    continue

                # Extract condition data
                coding = resource.get("code", {}).get("coding", [{}])[0]
                onset = resource.get(
                    "onsetDateTime", resource.get("onsetPeriod", {}).get("start", "")
                )

                conditions.append(
                    {
                        "code": coding.get("code", ""),
                        "name": coding.get("display", "Unknown condition"),
                        "onset_date": onset[:10] if onset else "unknown",
                        "status": resource.get("clinicalStatus", {})
                        .get("coding", [{}])[0]
                        .get("code", "active"),
                        "severity": resource.get("severity", {})
                        .get("coding", [{}])[0]
                        .get("display", "unknown"),
                    }
                )
        except Exception as e:
            logger.error(f"Error parsing FHIR conditions: {str(e)}")

        return conditions

    def _parse_fhir_observations(self, fhir_bundle: Dict) -> List[Dict]:
        """Parse FHIR Observation Bundle to simplified format."""
        observations = []
        try:
            entries = fhir_bundle.get("entry", [])
            for entry in entries:
                resource = entry.get("resource", {})
                if resource.get("resourceType") != "Observation":
                    continue

                # Extract observation data
                coding = resource.get("code", {}).get("coding", [{}])[0]
                value_quantity = resource.get("valueQuantity", {})

                # Check if abnormal
                interpretation = (
                    resource.get("interpretation", [{}])[0]
                    .get("coding", [{}])[0]
                    .get("code", "")
                )
                is_abnormal = interpretation in ["H", "L", "A", "AA", "HH", "LL"]

                observations.append(
                    {
                        "code": coding.get("code", ""),
                        "name": coding.get("display", "Unknown observation"),
                        "value": value_quantity.get("value", 0),
                        "unit": value_quantity.get("unit", ""),
                        "date": (
                            resource.get("effectiveDateTime", "")[:10]
                            if resource.get("effectiveDateTime")
                            else ""
                        ),
                        "is_abnormal": is_abnormal,
                        "reference_range": "",  # Could parse from referenceRange
                    }
                )
        except Exception as e:
            logger.error(f"Error parsing FHIR observations: {str(e)}")

        return observations

    def _parse_fhir_medications(self, fhir_bundle: Dict) -> List[Dict]:
        """Parse FHIR MedicationStatement Bundle to simplified format."""
        medications = []
        try:
            entries = fhir_bundle.get("entry", [])
            for entry in entries:
                resource = entry.get("resource", {})
                if resource.get("resourceType") not in [
                    "MedicationStatement",
                    "MedicationRequest",
                ]:
                    continue

                # Extract medication data
                med_code = resource.get("medicationCodeableConcept", {}).get(
                    "coding", [{}]
                )[0]
                med_name = med_code.get("display", "Unknown medication")

                medications.append(
                    {
                        "name": med_name,
                        "generic_name": med_name,  # Could parse from RxNorm
                        "class": "",  # Would need drug class lookup
                        "indication": "",  # Could parse from reasonCode
                        "start_date": (
                            resource.get("effectiveDateTime", "")[:10]
                            if resource.get("effectiveDateTime")
                            else ""
                        ),
                        "status": resource.get("status", "active"),
                    }
                )
        except Exception as e:
            logger.error(f"Error parsing FHIR medications: {str(e)}")

        return medications

    def _parse_fhir_allergies(self, fhir_bundle: Dict) -> List[Dict]:
        """Parse FHIR AllergyIntolerance Bundle to simplified format."""
        allergies = []
        try:
            entries = fhir_bundle.get("entry", [])
            for entry in entries:
                resource = entry.get("resource", {})
                if resource.get("resourceType") != "AllergyIntolerance":
                    continue

                # Extract allergy data
                coding = resource.get("code", {}).get("coding", [{}])[0]
                reaction = resource.get("reaction", [{}])[0]
                manifestation = reaction.get("manifestation", [{}])[0].get(
                    "coding", [{}]
                )[0]

                allergies.append(
                    {
                        "substance": coding.get("display", "Unknown substance"),
                        "reaction": manifestation.get("display", "Unknown reaction"),
                        "severity": reaction.get("severity", "unknown"),
                        "onset": (
                            resource.get("onsetDateTime", "")[:10]
                            if resource.get("onsetDateTime")
                            else ""
                        ),
                    }
                )
        except Exception as e:
            logger.error(f"Error parsing FHIR allergies: {str(e)}")

        return allergies

    # --- Public API methods (with mock fallback) ---

    async def get_patient_demographics(self, patient_id: str) -> Optional[Dict]:
        """Get patient demographics."""
        if self.use_mock:
            return self._get_mock_patient_demographics(patient_id)

        fhir_patient = await self._make_request("Patient", patient_id)
        if fhir_patient:
            parsed = self._parse_fhir_patient(fhir_patient)
            if parsed:
                return parsed

        # Fallback to mock
        logger.info(f"Falling back to mock data for patient {patient_id}")
        return self._get_mock_patient_demographics(patient_id)

    async def get_patient_conditions(
        self, patient_id: str, last_n_years: int = 10, active_only: bool = True
    ) -> List[Dict]:
        """Get patient conditions."""
        if self.use_mock:
            return self._get_mock_patient_conditions(
                patient_id, last_n_years, active_only
            )

        params = {"patient": patient_id}
        if active_only:
            params["clinical-status"] = "active"

        fhir_bundle = await self._make_request("Condition", params=params)
        if fhir_bundle:
            conditions = self._parse_fhir_conditions(fhir_bundle)
            if conditions:
                return conditions

        # Fallback to mock
        logger.info(f"Falling back to mock data for conditions of patient {patient_id}")
        return self._get_mock_patient_conditions(patient_id, last_n_years, active_only)

    async def get_patient_observations(
        self,
        patient_id: str,
        observation_codes: Optional[List[str]] = None,
        last_n_years: int = 10,
    ) -> List[Dict]:
        """Get patient observations (labs, vitals)."""
        if self.use_mock:
            return self._get_mock_patient_observations(patient_id, observation_codes)

        params = {"patient": patient_id, "_sort": "-date", "_count": "100"}
        if observation_codes:
            params["code"] = ",".join(observation_codes)

        fhir_bundle = await self._make_request("Observation", params=params)
        if fhir_bundle:
            observations = self._parse_fhir_observations(fhir_bundle)
            if observations:
                return observations

        # Fallback to mock
        logger.info(
            f"Falling back to mock data for observations of patient {patient_id}"
        )
        return self._get_mock_patient_observations(patient_id, observation_codes)

    async def get_patient_medications(
        self, patient_id: str, active_only: bool = True
    ) -> List[Dict]:
        """Get patient medications."""
        if self.use_mock:
            return self._get_mock_patient_medications(patient_id, active_only)

        params = {"patient": patient_id}
        if active_only:
            params["status"] = "active"

        fhir_bundle = await self._make_request("MedicationStatement", params=params)
        if fhir_bundle:
            medications = self._parse_fhir_medications(fhir_bundle)
            if medications:
                return medications

        # Fallback to mock
        logger.info(
            f"Falling back to mock data for medications of patient {patient_id}"
        )
        return self._get_mock_patient_medications(patient_id, active_only)

    async def get_patient_allergies(self, patient_id: str) -> List[Dict]:
        """Get patient allergies."""
        if self.use_mock:
            return self._get_mock_patient_allergies(patient_id)

        params = {"patient": patient_id}
        fhir_bundle = await self._make_request("AllergyIntolerance", params=params)
        if fhir_bundle:
            allergies = self._parse_fhir_allergies(fhir_bundle)
            if allergies:
                return allergies

        # Fallback to mock
        logger.info(f"Falling back to mock data for allergies of patient {patient_id}")
        return self._get_mock_patient_allergies(patient_id)

    async def get_complete_patient_history(self, patient_id: str) -> Dict:
        """Get complete patient history."""
        return {
            "demographics": await self.get_patient_demographics(patient_id),
            "conditions": await self.get_patient_conditions(patient_id),
            "observations": await self.get_patient_observations(
                patient_id, last_n_years=2
            ),
            "medications": await self.get_patient_medications(patient_id),
            "allergies": await self.get_patient_allergies(patient_id),
        }

    # --- Mock data methods (imported from original fhir_client.py) ---

    def _get_mock_patient_demographics(self, patient_id: str) -> Optional[Dict]:
        """Get mock patient demographics."""
        from app.tools.fhir_client import MOCK_PATIENTS

        return MOCK_PATIENTS.get(patient_id)

    def _get_mock_patient_conditions(
        self, patient_id: str, last_n_years: int = 10, active_only: bool = True
    ) -> List[Dict]:
        """Get mock patient conditions."""
        from app.tools.fhir_client import MOCK_CONDITIONS

        conditions = MOCK_CONDITIONS.get(patient_id, [])
        if active_only:
            conditions = [c for c in conditions if c.get("status") == "active"]
        return conditions

    def _get_mock_patient_observations(
        self, patient_id: str, observation_codes: Optional[List[str]] = None
    ) -> List[Dict]:
        """Get mock patient observations."""
        from app.tools.fhir_client import MOCK_OBSERVATIONS

        observations = MOCK_OBSERVATIONS.get(patient_id, [])
        if observation_codes:
            observations = [
                obs for obs in observations if obs["code"] in observation_codes
            ]
        observations.sort(key=lambda x: x["date"], reverse=True)
        return observations

    def _get_mock_patient_medications(
        self, patient_id: str, active_only: bool = True
    ) -> List[Dict]:
        """Get mock patient medications."""
        from app.tools.fhir_client import MOCK_MEDICATIONS

        medications = MOCK_MEDICATIONS.get(patient_id, [])
        if active_only:
            medications = [m for m in medications if m.get("status") == "active"]
        return medications

    def _get_mock_patient_allergies(self, patient_id: str) -> List[Dict]:
        """Get mock patient allergies."""
        from app.tools.fhir_client import MOCK_ALLERGIES

        return MOCK_ALLERGIES.get(patient_id, [])


# --- Global client instance ---

_fhir_client: Optional[FHIRClient] = None


def get_fhir_client() -> FHIRClient:
    """Get or create global FHIR client instance."""
    global _fhir_client
    if _fhir_client is None:
        _fhir_client = FHIRClient()
    return _fhir_client


# --- Convenience functions (async wrappers for compatibility) ---


async def get_patient_demographics(patient_id: str) -> Optional[Dict]:
    """Get patient demographics (async)."""
    client = get_fhir_client()
    return await client.get_patient_demographics(patient_id)


async def get_patient_conditions(
    patient_id: str, last_n_years: int = 10, active_only: bool = True
) -> List[Dict]:
    """Get patient conditions (async)."""
    client = get_fhir_client()
    return await client.get_patient_conditions(patient_id, last_n_years, active_only)


async def get_patient_observations(
    patient_id: str,
    observation_codes: Optional[List[str]] = None,
    last_n_years: int = 10,
) -> List[Dict]:
    """Get patient observations (async)."""
    client = get_fhir_client()
    return await client.get_patient_observations(
        patient_id, observation_codes, last_n_years
    )


async def get_patient_medications(
    patient_id: str, active_only: bool = True
) -> List[Dict]:
    """Get patient medications (async)."""
    client = get_fhir_client()
    return await client.get_patient_medications(patient_id, active_only)


async def get_patient_allergies(patient_id: str) -> List[Dict]:
    """Get patient allergies (async)."""
    client = get_fhir_client()
    return await client.get_patient_allergies(patient_id)


async def get_complete_patient_history(patient_id: str) -> Dict:
    """Get complete patient history (async)."""
    client = get_fhir_client()
    return await client.get_complete_patient_history(patient_id)
