"""Tipos de dados usados em todo o projeto."""

from dataclasses import dataclass


@dataclass
class Channel:
    name: str  # ex.: "L1 670nm"
    x: list
    y: list


@dataclass
class Level:
    label: str
    start: float  # min (tempo já zerado, coluna C)
    end: float


class InputError(ValueError):
    """Erro causado pelo arquivo ou pelos dados enviados; a mensagem é segura para mostrar ao usuário."""
