"""Frases fijas con variantes (phrases.py) y tono del prompt de sistema (6.15)."""

import itertools
import random
from typing import get_args

from nyx.brain.base import LLMErrorKind
from nyx.brain.phrases import LLM_ERROR_KEY, PHRASES, PhraseBook
from nyx.brain.prompts import system_prompt
from nyx.brain.service import Brain
from nyx.settings.model import ResponseTone
from tests.test_pipeline import FakeLLM


def test_every_phrase_group_has_variants_and_never_repeats_consecutive() -> None:
    book = PhraseBook(random.Random(42))
    assert {"done", "not_understood", "garbled", "error_stt"} <= PHRASES.keys()
    for kind in LLMErrorKind:
        assert LLM_ERROR_KEY[kind] in PHRASES
    for key, options in PHRASES.items():
        assert 2 <= len(options) <= 3
        assert all(p.display for p in options)
        picks = [book.pick(key) for _ in range(12)]
        assert len(set(picks)) >= 2
        for a, b in itertools.pairwise(picks):
            assert a != b


def test_llm_error_lookup_does_not_repeat() -> None:
    book = PhraseBook(random.Random(7))
    first = book.llm_error(LLMErrorKind.UNAVAILABLE)
    second = book.llm_error(LLMErrorKind.UNAVAILABLE)
    assert first != second
    assert first.spoken and second.spoken


def test_system_prompt_only_differs_in_one_paragraph_per_tone() -> None:
    tones = get_args(ResponseTone)
    assert set(tones) == {"cercano", "neutro", "divertido"}
    prompts = {tone: system_prompt(tone) for tone in tones}
    for tone, text in prompts.items():
        assert "como mucho 2 frases" in text
        assert "De nada, estaré aquí" in text
        assert len(text.split("\n\n")) == len(prompts["cercano"].split("\n\n"))
        # Solo cambia el primer bloque (donde va el párrafo de tono); el resto es idéntico.
        head, rest = text.split("\n\n", 1)
        ref_head, ref_rest = prompts["cercano"].split("\n\n", 1)
        assert rest == ref_rest
        if tone != "cercano":
            assert head != ref_head


def test_brain_fixes_system_prompt_at_startup() -> None:
    brain_fun = Brain(FakeLLM(), tone="divertido")
    brain_neutral = Brain(FakeLLM(), tone="neutro")
    msg_fun = brain_fun.build_messages("hola")[0].content
    msg_neutral = brain_neutral.build_messages("hola")[0].content
    assert msg_fun == system_prompt("divertido")
    assert msg_neutral == system_prompt("neutro")
    assert brain_fun.build_messages("otra")[0].content == msg_fun
