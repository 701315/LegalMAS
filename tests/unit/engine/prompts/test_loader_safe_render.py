from pathlib import Path

from engine.prompts.loader import PromptLoader


def test_load_replaces_only_explicit_placeholders_and_preserves_json_keys(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = prompts_dir / "test_prompt.txt"
    prompt_file.write_text(
        """
Контекст:
{context}

Верни JSON:
{"found": true, "evidence": "...", "confidence": 0.9}
        """.strip(),
        encoding="utf-8",
    )

    loader = PromptLoader(prompts_root=prompts_dir)
    rendered = loader.load("test_prompt", {"context": "Текст договора"})

    assert "Текст договора" in rendered
    assert '{"found": true, "evidence": "...", "confidence": 0.9}' in rendered


    