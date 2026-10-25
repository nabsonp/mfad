"""
Leitores de composição por template.

Onde o framework liga um componente a outro pelo template, e não por
import, o alcance precisa de quem leia essa ligação. Hoje só o
Angular faz assim; no React o JSX usa um identificador importado, e
o import já basta.
"""

from mfad.adapters.driven.reconstruction.templates.angular import (
    AngularTemplates,
)

__all__ = ["AngularTemplates"]
