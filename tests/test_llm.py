from src.llm import build_spc


def test_build_spc_returns_expected_shape():
    result = build_spc("the library has no quiet study pods")

    assert result["need"]
    assert result["problem_statement"]
    assert result["target_user"]
    assert result["solution_concept"]
    assert result["evidence"]
    assert len(result["components"]) == 4
