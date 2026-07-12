import re
from typing import Dict, Any, List, Optional

class SAPAgenticService:
    # In-memory stand-in for a session/token cache. This is demo-only data
    # (see authenticate_notes_server below) and was previously persisted to
    # a plaintext token-cache.json file on disk; there's no reason fake
    # simulated credentials should survive a process restart or live on
    # disk, so this is now a module-level dict instead.
    _TOKEN_CACHE: Dict[str, Any] = {}

    # A local dictionary of simulated standard SAP Notes
    SIMULATED_NOTES = {
        "2187425": {
            "note_number": "2187425",
            "title": "TCI Note Assistant Bootstrap for SAP_BASIS 700 to 702",
            "delivery_format": "Transport-Based Correction (TCI) SAR Archive",
            "modification_depth": "Deep repository adjustments including DDIC structures and table changes",
            "prerequisites": [],
            "release_range": "SAP_BASIS 700 - 702",
            "manual_steps": "1. Import the bootstrap container.\n2. Execute Note Assistant enablement reports.\n3. Validate SNOTE TCI configuration.",
            "signed": True
        },
        "2732094": {
            "note_number": "2732094",
            "title": "Automated Notes Search Tool (ANST) Support Backbone Integration",
            "delivery_format": "Digitally Signed SAP Note (XML structure)",
            "modification_depth": "Standard code changes to ANST integration classes",
            "prerequisites": ["2020356"],
            "release_range": "SAP_BASIS 700 and above",
            "manual_steps": "1. Run SNOTE to import standard correction.\n2. Configure RFC connection for support backbone in SM59.",
            "signed": True
        },
        "2020356": {
            "note_number": "2020356",
            "title": "Performance Assistant Note Search (PANKS) Tool Installation",
            "delivery_format": "Plain text code corrections",
            "modification_depth": "Limited to SE61 help texts and message handler class updates",
            "prerequisites": [],
            "release_range": "SAP_BASIS 700 and above",
            "manual_steps": "Apply code adjustments in function module 'SE61_TEXT_SEARCH'.",
            "signed": False
        }
    }

    @staticmethod
    def analyze_runtime_dump(dump_text: str) -> Dict[str, Any]:
        """
        Parses ST22 system short dumps, performs Source Code Attribution,
        and determines appropriate troubleshooting steps.
        """
        # Extract exception, program, transaction code
        exception_match = re.search(r"Runtime Error\s+([\w_]+)", dump_text, re.IGNORECASE)
        exception_name = exception_match.group(1) if exception_match else "UNKNOWN_ERROR"
        
        prog_match = re.search(r"(?:Program|Triggering Program|Main Program)\s+([\w_/\\=-]+)", dump_text, re.IGNORECASE)
        program_name = prog_match.group(1) if prog_match else "UNKNOWN_PROGRAM"

        tcode_match = re.search(r"Transaction\s+(\w+)", dump_text, re.IGNORECASE)
        tcode = tcode_match.group(1) if tcode_match else "N/A"

        # Determine attribution (Standard SAP vs Custom Code)
        # Custom code typically starts with Z, Y, or contains custom namespaces like /Z.../
        is_custom = False
        clean_prog = program_name.upper().strip()
        if clean_prog.startswith('Z') or clean_prog.startswith('Y') or clean_prog.startswith('/Z') or clean_prog.startswith('/Y'):
            is_custom = True
            attribution = "Custom Code Block"
        else:
            attribution = "Standard SAP Code Block"

        # Parsing diagnostic pipeline simulation
        pipeline = [
            {"step": "Log Parsing Engine", "status": "Completed", "detail": f"Parsed short dump structure. Exception: {exception_name}"},
            {"step": "Source Code Attribution", "status": "Completed", "detail": f"Attributed to {attribution} ({program_name})"}
        ]

        analysis_details = ""
        recommendations = []

        if is_custom:
            pipeline.append({"step": "Local Static Analysis & Linters", "status": "Completed", "detail": "Ran local syntax checks on custom program."})
            analysis_details = f"The failure occurred in custom enhancement program {program_name}. A code quality and compliance scan is recommended."
            recommendations = [
                "Scan the custom source code using the Clean Core compliance engine to detect unreleased API usage.",
                "Review active BAdI implementations (specifically USMD_RULE_SERVICE BAdI implementations if governing Master Data).",
                "Ensure local variable initialization and reference object validation (e.g. check for null objects before invocation)."
            ]
        else:
            pipeline.append({"step": "Support Portal Queries", "status": "Completed", "detail": "Launches automated ANST/PANKS metadata search."})
            pipeline.append({"step": "Programmatic Note Fetch", "status": "Completed", "detail": "Discovered matching standard SAP Note corrections."})
            
            analysis_details = f"The dump occurred inside standard SAP repository namespace. This indicates a missing standard correction."
            
            # Map exception/program to notes
            if "OBJREF" in exception_name or "OBJECTS_OBJREF_NOT_ASSIGNED" in exception_name:
                notes = [SAPAgenticService.SIMULATED_NOTES["2732094"]]
                recommendations.append("Apply standard SAP Note 2732094 to resolve standard ANST/Backbone references.")
            else:
                notes = [SAPAgenticService.SIMULATED_NOTES["2020356"]]
                recommendations.append("Review standard Note 2020356 to update error message handler class fields.")
                
            recommendations.append("Use transaction SNOTE to import the recommended correction packages.")
            recommendations.append("Ensure your SAP_BASIS application release aligns with the note requirements.")

        return {
            "exception": exception_name,
            "program": program_name,
            "tcode": tcode,
            "attribution": attribution,
            "is_custom": is_custom,
            "pipeline": pipeline,
            "analysis_details": analysis_details,
            "recommendations": recommendations
        }

    @staticmethod
    def authenticate_notes_server(auth_mode: str, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Simulates SNOTE dual-mode authentication server (Model Context Protocol).

        This is demo authentication only: any non-empty username/password is
        accepted and no real SAP Support Portal / S-user connection is ever
        made. The resulting fake session is cached in-memory only
        (SAPAgenticService._TOKEN_CACHE) for the lifetime of the process —
        it is never written to disk.
        """
        if auth_mode == "certificate":
            # PFX TLS handshake login
            session_cookie = "sec-session-cert-mode-99281a88bb3e72"
            status = "Authenticated via TLS Handshake (Client PFX Certificate Mode)"
        else:
            if not username or not password:
                return {"success": False, "message": "Username and password credentials are required for form-based login."}
            # IAS credentials mode simulator
            session_cookie = "sec-session-credentials-mode-1122aa77bb"
            status = "Authenticated via Credentials (IAS Login Mode)"

        # Cache session in-memory only (demo data, not persisted to disk)
        cache_data = {
            "session_cookie": session_cookie,
            "auth_mode": auth_mode,
            "user": username or "SAP Passport SSL Certificate",
            "expires_in_hours": 24
        }
        SAPAgenticService._TOKEN_CACHE.clear()
        SAPAgenticService._TOKEN_CACHE.update(cache_data)

        return {
            "success": True,
            "status": status,
            "session_cookie": session_cookie,
            "cache_saved": True
        }

    @staticmethod
    def get_note_details(note_number: str, sap_basis_version: str = "750") -> Dict[str, Any]:
        """
        Retrieves note details and checks base release compatibility.
        """
        # Strip leading zeros or spaces
        clean_no = note_number.strip().lstrip("0")
        note = SAPAgenticService.SIMULATED_NOTES.get(clean_no)
        
        if not note:
            return {
                "found": False,
                "message": f"SAP Note {note_number} was not found in the local repository."
            }

        # Check NetWeaver base release warning
        basis_num = int(re.sub(r"\D", "", sap_basis_version))
        low_release_warning = False
        warning_msg = ""
        
        if basis_num >= 700 and basis_num <= 702:
            low_release_warning = True
            warning_msg = (
                f"WARNING: Your SAP_BASIS version is {sap_basis_version} (Low Release). "
                "The Note Assistant lacks the ability to process Transport-Based Correction Instructions (TCI) by default. "
                "Please implement bootstrap SAP Note 2187425 before attempting SNOTE imports."
            )

        return {
            "found": True,
            "note_details": note,
            "low_release_warning": low_release_warning,
            "warning_message": warning_msg
        }

    @staticmethod
    def validate_abap_code(code_text: str) -> Dict[str, Any]:
        """
        Executes compile-time and run-time validation rules over ABAP code.
        Assigns Clean Core Level Grade (A to D) based on clean-core guidelines.
        """
        violations = []
        
        # 1. Check for direct database updates/queries to standard master data tables
        db_tables = ['MARA', 'BUT000', 'KNA1', 'LFA1', 'VBAK', 'EKKO']
        for table in db_tables:
            pattern = rf"\bFROM\s+{table}\b"
            if re.search(pattern, code_text, re.IGNORECASE):
                violations.append({
                    "rule": "Clean Core Core Data Rules",
                    "severity": "High",
                    "message": f"Direct database query to standard table {table} detected. Use released CDS view entities (e.g. I_BusinessPartnerTP) instead."
                })
            
            update_pattern = rf"\b(?:UPDATE|INSERT|DELETE|MODIFY)\s+{table}\b"
            if re.search(update_pattern, code_text, re.IGNORECASE):
                violations.append({
                    "rule": "Clean Core Transactional Rules",
                    "severity": "Critical",
                    "message": f"Direct database modification to standard table {table} detected. Database updates are blocked in Clean ABAP Cloud Ready Mode."
                })

        # 2. Check for Entity Manipulation Language (EML) usage (READ ENTITIES OF / MODIFY ENTITIES OF)
        eml_present = False
        if re.search(r"\bREAD\s+ENTITIES\s+OF\b", code_text, re.IGNORECASE):
            eml_present = True

        # 3. Check for obsolete ABAP keywords
        obsolete_keywords = ['MOVE', 'OCCURS', 'LIKE', 'COMPUTE', 'RANGES']
        for keyword in obsolete_keywords:
            if re.search(rf"\b{keyword}\b", code_text, re.IGNORECASE):
                violations.append({
                    "rule": "Clean ABAP Syntax Rules",
                    "severity": "Medium",
                    "message": f"Obsolete ABAP keyword '{keyword}' detected. Use modern assignment operators or types."
                })

        # 4. Check for direct use of unreleased standard validation classes
        if re.search(r"\bCL_USMD_RULE_SERVICE\b", code_text, re.IGNORECASE) or re.search(r"\bUSMD_RULE_SERVICE\b", code_text, re.IGNORECASE):
            violations.append({
                "rule": "Release Stability Rules",
                "severity": "Medium",
                "message": "Usage of classic validation service USMD_RULE_SERVICE detected. Use RAP Business Object determinations and validations in Cloud-Ready mode."
            })

        # 5. Determine Compliance Grade
        if any(v["severity"] == "Critical" for v in violations):
            grade = "Level D"
            status = "Legacy Non-Compliant"
            description = "Direct database modifications or standard updates bypass standard staging logic. High upgrade risks."
        elif any(v["severity"] == "High" for v in violations):
            grade = "Level C"
            status = "Controlled Classic"
            description = "Direct database queries or unreleased API calls are present. Restrict standard calls to isolated custom packages using strict BAdI spots."
        elif len(violations) > 0:
            grade = "Level B"
            status = "Managed Wrapper"
            description = "Custom code uses standard unreleased wrappers. Minor compliance issues or obsolete keywords present."
        else:
            grade = "Level A"
            status = "Fully Compliant"
            description = "ABAP Cloud Standard. Code uses only released APIs, CDS view entities (e.g. I_BusinessPartnerTP), and EML syntax. Upgrade-stable."

        # Online Compilation simulation
        adt_status = "Success"
        unit_test_status = "Passed (1 unit test executed successfully)"
        if grade == "Level D":
            adt_status = "Warnings"
            unit_test_status = "Failed (Checks aborted due to direct update constraints)"

        return {
            "grade": grade,
            "status": status,
            "description": description,
            "violations": violations,
            "gates": {
                "offline_linter": "Completed with warnings" if violations else "Completed successfully (100% compliant)",
                "online_compilation": f"ADT Activation {adt_status} ($TMP namespace)",
                "unit_test_validation": unit_test_status
            },
            "remediation_advice": (
                "Rewrite database select structures using RAP Entity Manipulation Language.\n"
                "Example compliant code: \n"
                "READ ENTITIES OF i_businesspartnertp\n"
                "  ENTITY BusinessPartner\n"
                "    FIELDS ( BusinessPartner BusinessPartnerName )\n"
                "    WITH VALUE #( ( %key-BusinessPartner = iv_bp_id ) )\n"
                "  RESULT DATA(lt_bp_results)."
            )
        }
