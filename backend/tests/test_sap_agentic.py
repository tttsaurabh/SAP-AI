import pytest
from app.services.sap_agentic_service import SAPAgenticService

def test_analyze_runtime_dump_standard():
    dump_text = (
        "Runtime Error         OBJECTS_OBJREF_NOT_ASSIGNED\n" +
        "Exception             CX_SY_REF_IS_INITIAL\n" +
        "Triggering Program    CL_USMD_RULE_SERVICE==========CP\n" +
        "Transaction           MDGIMG"
    )
    result = SAPAgenticService.analyze_runtime_dump(dump_text)
    assert result["exception"] == "OBJECTS_OBJREF_NOT_ASSIGNED"
    assert result["program"] == "CL_USMD_RULE_SERVICE==========CP"
    assert result["attribution"] == "Standard SAP Code Block"
    assert not result["is_custom"]
    assert len(result["recommendations"]) > 0
    assert any("2732094" in rec for rec in result["recommendations"])

def test_analyze_runtime_dump_custom():
    dump_text = (
        "Runtime Error         ASSIGN_CAST_WRONG_TYPE\n" +
        "Triggering Program    ZCL_CUSTOM_BP_ENHANCEMENT====CP\n" +
        "Transaction           MDGIMG"
    )
    result = SAPAgenticService.analyze_runtime_dump(dump_text)
    assert result["exception"] == "ASSIGN_CAST_WRONG_TYPE"
    assert result["program"] == "ZCL_CUSTOM_BP_ENHANCEMENT====CP"
    assert result["attribution"] == "Custom Code Block"
    assert result["is_custom"]
    assert any("Clean Core" in rec for rec in result["recommendations"])

def test_note_details_standard():
    result = SAPAgenticService.get_note_details("2732094", "750")
    assert result["found"]
    assert result["note_details"]["note_number"] == "2732094"
    assert not result["low_release_warning"]

def test_note_details_low_release():
    result = SAPAgenticService.get_note_details("2732094", "702")
    assert result["found"]
    assert result["low_release_warning"]
    assert "bootstrap SAP Note 2187425" in result["warning_message"]

def test_validate_code_compliant():
    code = (
        "CLASS zcl_mdg_bp_reader DEFINITION.\n" +
        "  METHOD read_bp.\n" +
        "    READ ENTITIES OF i_businesspartnertp\n" +
        "      ENTITY BusinessPartner\n" +
        "        ALL FIELDS WITH VALUE #( ( BusinessPartner = '123' ) )\n" +
        "      RESULT DATA(lt_bp).\n" +
        "  ENDMETHOD.\n" +
        "ENDCLASS."
    )
    result = SAPAgenticService.validate_abap_code(code)
    assert result["grade"] == "Level A"
    assert result["status"] == "Fully Compliant"
    assert len(result["violations"]) == 0

def test_validate_code_non_compliant():
    code = (
        "CLASS zcl_bad_code DEFINITION.\n" +
        "  METHOD bad_method.\n" +
        "    UPDATE mara SET vpsta = 'X' WHERE matnr = '100'.\n" +
        "  ENDMETHOD.\n" +
        "ENDCLASS."
    )
    result = SAPAgenticService.validate_abap_code(code)
    assert result["grade"] == "Level D"
    assert result["status"] == "Legacy Non-Compliant"
    assert len(result["violations"]) > 0
    assert any("direct database modification" in v["message"].lower() for v in result["violations"])
