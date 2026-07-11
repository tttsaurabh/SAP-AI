from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.core.security import any_authenticated
from app.models.models import User
from app.services.sap_agentic_service import SAPAgenticService

router = APIRouter(prefix="/api/sap-agentic", tags=["sap-agentic"])

# Request/Response Schemas
class DumpAnalysisRequest(BaseModel):
    dump_text: str

class NoteSearchRequest(BaseModel):
    note_number: str
    sap_basis_version: str = "750"

class CodeValidationRequest(BaseModel):
    code_text: str

class AuthenticateNotesRequest(BaseModel):
    auth_mode: str # 'certificate' or 'credentials'
    username: Optional[str] = None
    password: Optional[str] = None

class IntegrationSpecRequest(BaseModel):
    target_system: str # 'crm', 'warehouse', 'datalake', 'saas'
    encryption_enabled: bool = True

@router.post("/analyze-dump")
def analyze_dump(
    request: DumpAnalysisRequest,
    current_user: User = Depends(any_authenticated)
):
    try:
        return SAPAgenticService.analyze_runtime_dump(request.dump_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze ST22 runtime dump: {str(e)}"
        )

@router.post("/search-notes")
def search_notes(
    request: NoteSearchRequest,
    current_user: User = Depends(any_authenticated)
):
    try:
        return SAPAgenticService.get_note_details(request.note_number, request.sap_basis_version)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch SAP note: {str(e)}"
        )

@router.post("/authenticate-notes")
def authenticate_notes(
    request: AuthenticateNotesRequest,
    current_user: User = Depends(any_authenticated)
):
    try:
        return SAPAgenticService.authenticate_notes_server(
            request.auth_mode, request.username, request.password
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication handshake failed: {str(e)}"
        )

@router.post("/validate-code")
def validate_code(
    request: CodeValidationRequest,
    current_user: User = Depends(any_authenticated)
):
    try:
        return SAPAgenticService.validate_abap_code(request.code_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code validation run failed: {str(e)}"
        )

@router.get("/transition-guide")
def get_transition_guide(
    current_user: User = Depends(any_authenticated)
):
    # Transition guidelines as configured in the customized IMG guide of standard Cloud-Ready Mode
    return {
        "steps": [
            {
                "id": 1,
                "title": "Customizing Transaction Access",
                "action": "Execute transaction MDGIMG to open the Master Data Governance implementation guide.",
                "status": "Required"
            },
            {
                "id": 2,
                "title": "Switching Mode Activation",
                "action": "Drill down into Master Data Governance -> Cloud-Ready Mode in SAP MDG -> Switch for Cloud-Ready Mode in SAP MDG.",
                "status": "Required"
            },
            {
                "id": 3,
                "title": "Domain Configuration Entry",
                "action": "Select New Entries and map Object Type Code representing Business Partner domain (or Material master if supported).",
                "status": "Required"
            },
            {
                "id": 4,
                "title": "Enabling the Switch Flag",
                "action": "Select checkbox 'Cloud-Ready Mode Switched On' and assign to a transport request.",
                "status": "Required"
            },
            {
                "id": 5,
                "title": "Predefined Template Import",
                "action": "Activate standard Business Configuration Sets (BC Sets) to load default process workflows, mass-processing rules, and validations.",
                "status": "Recommended"
            },
            {
                "id": 6,
                "title": "SAP Build Process Automation Integration",
                "action": "Establish communication with SAP BTP process automation templates to orchestrate federated governance workflows.",
                "status": "Recommended"
            }
        ],
        "coexistence_checks": [
            "Parallel Active Areas verification in database tables.",
            "Classic UI mapping checks (Web Dynpro and Floorplan Manager coexistence alongside Fiori Elements).",
            "BAdI replication checks: review legacy validations in USMD_RULE_SERVICE for compatibility."
        ]
    }

@router.post("/integration-spec")
def get_integration_spec(
    request: IntegrationSpecRequest,
    current_user: User = Depends(any_authenticated)
):
    specs = {
        "crm": {
            "title": "Salesforce CRM Integration",
            "pattern": "Synchronous RESTful validation & account publishing",
            "protocol": "HTTPS / JSON OData Service (OData V4)",
            "adapter": "Salesforce Adapter / HTTP Receiver in SAP Cloud Integration",
            "security": "API Management Gateway with rate-limiting, SSL termination, and client certificates (mTLS)",
            "steps": [
                "1. Expose standard business partner outbound OData service.",
                "2. Route request to SAP Cloud Integration tenant.",
                "3. Authenticate with Salesforce OAuth2 endpoint.",
                "4. Perform fields transformation and execute synchronous validation."
            ]
        },
        "warehouse": {
            "title": "Enterprise Data Warehouse / Solace Mesh",
            "pattern": "Decoupled, high-volume asynchronous publishing",
            "protocol": "Advanced Message Queuing Protocol (AMQP)",
            "adapter": "AMQP Adapter on SAP Event Mesh / Solace Queue Receiver",
            "security": "Queue-based client certificates authentication and message payload signature checks",
            "steps": [
                "1. Configure DRF (Data Replication Framework) replication model in transaction DRFIMG.",
                "2. Assign event triggers to outbound Business Partner / Material changes.",
                "3. Replicate outbound data payloads to SAP Event Mesh Topic.",
                "4. Distribute to Solace broker / Warehouse subscriber queue for ingestion."
            ]
        },
        "datalake": {
            "title": "Hyperscaler Lakehouses (AWS S3 / Google Cloud Storage)",
            "pattern": "Bulk extraction and batch file replication",
            "protocol": "SFTP / SOAP XML",
            "adapter": "Redwood RunMyJobs triggers / SFTP Sender Adapter",
            "security": "Managed file transfers using secure SSH keys and PGP encryption",
            "steps": [
                "1. Generate daily master data change delta files.",
                "2. Execute bulk extraction reports in background.",
                "3. Transfer extracted XML/CSV files via Redwood automated workflows to cloud storage bucket.",
                "4. Validate file hashes upon delivery."
            ]
        },
        "saas": {
            "title": "SaaS Applications (Ariba / Concur)",
            "pattern": "Aligned Master Data Distribution via Central Hub",
            "protocol": "SOAP Web Services",
            "adapter": "SAP Master Data Integration (MDI) Client Adapter",
            "security": "mTLS Authentication using secure client certificates issued via SAP Passport backbone",
            "steps": [
                "1. Register SAP S/4HANA (MDG) client instance in BTP Master Data Orchestration.",
                "2. Create company code / purchasing org routing rules.",
                "3. Connect S/4HANA to SAP MDI using mTLS secure certificates.",
                "4. Sync core global records via One Domain Model standard definitions."
            ]
        }
    }

    selected = specs.get(request.target_system.lower())
    if not selected:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown integration target system: {request.target_system}"
        )
    return selected
