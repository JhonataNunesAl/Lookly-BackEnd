"""Dígito verificador de CPF/CNPJ — confere só o FORMATO (é matematicamente
coerente), não se a empresa/pessoa existe de verdade. Para CNPJ, a existência
real é checada à parte via `core/cnpj_lookup.py` (BrasilAPI). Não existe
registro público equivalente para CPF.
"""

import re


def normalizar_documento(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def validar_cpf(digits: str) -> bool:
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    def digito(fatia: str, pesos: range) -> int:
        soma = sum(int(d) * p for d, p in zip(fatia, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = digito(digits[:9], range(10, 1, -1))
    if d1 != int(digits[9]):
        return False
    d2 = digito(digits[:10], range(11, 1, -1))
    return d2 == int(digits[10])


def validar_cnpj(digits: str) -> bool:
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    def digito(fatia: str, pesos: list[int]) -> int:
        soma = sum(int(d) * p for d, p in zip(fatia, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = digito(digits[:12], pesos1)
    if d1 != int(digits[12]):
        return False
    d2 = digito(digits[:13], pesos2)
    return d2 == int(digits[13])


def validar_documento(digits: str, tipo: str) -> bool:
    return validar_cpf(digits) if tipo == "CPF" else validar_cnpj(digits)
