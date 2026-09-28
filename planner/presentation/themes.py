"""Colour palettes. Each theme's tokens become CSS custom properties on :root."""

from __future__ import annotations

from .base import Presentation, PresentationRegistry

class Theme(Presentation):
    """A colour palette. `tokens` are emitted as CSS custom properties on :root."""

    tokens: dict[str, str] = {}

    def describe(self) -> dict[str, Any]:
        payload = super().describe()
        payload["tokens"] = self.tokens
        return payload


class ZarimanTheme(Theme):
    key = "zariman"
    label = "Zariman"
    description = "Warm neutral greys with sea-green accents."
    tokens = {
        "bg": "#1a1a19",
        "surface": "#232322",
        "surface-2": "#2b2b29",
        "surface-3": "#353532",
        "border": "#3e3e3a",
        "text": "#f0efe9",
        "text-dim": "#a8a79e",
        "text-faint": "#79786f",
        "accent": "#4fb3a3",
        "accent-ink": "#07231f",
        "danger": "#df7c6d",
        "ok": "#63b98f",
        "warn": "#d3a65c",
        "row-alt": "#1f1f1e",
        "row-hover": "#2b2b29",
        "row-selected": "#2c3a37",
        "head-bg": "#1f1f1e",
    }


class OrokinTheme(Theme):
    key = "orokin"
    label = "Orokin"
    description = "Lacquered gold on black, the Prime aesthetic."
    tokens = {
        "bg": "#0d0c09",
        "surface": "#181510",
        "surface-2": "#221e16",
        "surface-3": "#2e281c",
        "border": "#3b3325",
        "text": "#f4eddc",
        "text-dim": "#b6a683",
        "text-faint": "#7d7156",
        "accent": "#d4af5f",
        "accent-ink": "#181307",
        "danger": "#d96a4e",
        "ok": "#9cbb63",
        "warn": "#e0a63c",
        "row-alt": "#12100b",
        "row-hover": "#221e16",
        "row-selected": "#2f2718",
        "head-bg": "#121009",
    }


class CorpusTheme(Theme):
    key = "corpus"
    label = "Corpus"
    description = "Clinical slate and cyan, lit like a Corpus ship."
    tokens = {
        "bg": "#0c1116",
        "surface": "#141c24",
        "surface-2": "#1c2733",
        "surface-3": "#26333f",
        "border": "#2f3f4d",
        "text": "#e4eef5",
        "text-dim": "#9ab0c0",
        "text-faint": "#68808f",
        "accent": "#38bdf8",
        "accent-ink": "#041018",
        "danger": "#f0685f",
        "ok": "#2dd4a7",
        "warn": "#f2b134",
        "row-alt": "#101820",
        "row-hover": "#1c2733",
        "row-selected": "#1e3444",
        "head-bg": "#0f161d",
    }


class GrineerTheme(Theme):
    key = "grineer"
    label = "Grineer"
    description = "Rust, brass and riveted iron."
    tokens = {
        "bg": "#131110",
        "surface": "#1d1a17",
        "surface-2": "#26221e",
        "surface-3": "#332d27",
        "border": "#3f3730",
        "text": "#ece5dc",
        "text-dim": "#ad9f91",
        "text-faint": "#7a6e62",
        "accent": "#c9743c",
        "accent-ink": "#150c05",
        "danger": "#cf5340",
        "ok": "#8fa356",
        "warn": "#d99a35",
        "row-alt": "#181513",
        "row-hover": "#26221e",
        "row-selected": "#33271d",
        "head-bg": "#171412",
    }


class InfestedTheme(Theme):
    key = "infested"
    label = "Infested"
    description = "Bile green and raw flesh on rot-dark."
    tokens = {
        "bg": "#0e120d",
        "surface": "#161c14",
        "surface-2": "#1e261b",
        "surface-3": "#293224",
        "border": "#343f2d",
        "text": "#e6ecdd",
        "text-dim": "#9fae91",
        "text-faint": "#6d7b62",
        "accent": "#a3c93f",
        "accent-ink": "#0c1305",
        "danger": "#d9607a",
        "ok": "#7fce6b",
        "warn": "#e2b23e",
        "row-alt": "#121710",
        "row-hover": "#1e261b",
        "row-selected": "#26321f",
        "head-bg": "#121710",
    }



DEFAULT_THEME = "zariman"


def default_themes() -> PresentationRegistry:
    registry = PresentationRegistry(fallback=DEFAULT_THEME)
    for theme in (ZarimanTheme(), OrokinTheme(), CorpusTheme(),
                  GrineerTheme(), InfestedTheme()):
        registry.register(theme)
    return registry
