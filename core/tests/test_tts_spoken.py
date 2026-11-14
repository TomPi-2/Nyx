import pytest

from nyx.tts.spoken import number_words, to_spoken


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "cero"),
        (1, "uno"),
        (16, "dieciséis"),
        (21, "veintiuno"),
        (31, "treinta y uno"),
        (100, "cien"),
        (101, "ciento uno"),
        (391, "trescientos noventa y uno"),
        (500, "quinientos"),
        (1000, "mil"),
        (2026, "dos mil veintiséis"),
        (21000, "veintiún mil"),
        (101000, "ciento un mil"),
        (1_000_000, "un millón"),
        (2_500_000, "dos millones quinientos mil"),
        (-5, "menos cinco"),
    ],
)
def test_number_words(n: int, words: str) -> None:
    assert number_words(n) == words


def test_feminine_for_hours() -> None:
    assert number_words(1, feminine=True) == "una"
    assert number_words(21, feminine=True) == "veintiuna"


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        (
            "Cuenta del 1 al 10: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10.",
            "Cuenta del uno al diez: uno, dos, tres, cuatro, cinco, seis, siete, ocho, nueve, "
            "diez.",
        ),
        ("Son las 21:36.", "Son las veintiuna y treinta y seis."),
        ("A las 7:30 y a las 10:15.", "A las siete y media y a las diez y cuarto."),
        ("Son las 9:00.", "Son las nueve en punto."),
        ("Volumen al 50 %", "Volumen al cincuenta por ciento"),
        ("Hace 18 °C", "Hace dieciocho grados"),
        ("Cuesta 3,50 €", "Cuesta tres coma cincuenta euros"),
        ("Pi vale 3.14", "Pi vale tres coma catorce"),
        ("Hay 25.000 personas", "Hay veinticinco mil personas"),
        ("17 x 23 = 391", "diecisiete por veintitrés igual a trescientos noventa y uno"),
        ("Hace -3 grados", "Hace menos tres grados"),
        ("En 2026", "En dos mil veintiséis"),
        ("Hola, ¿qué tal?", "Hola, ¿qué tal?"),
        (
            "IP: 192.168.1.36",
            "IP: ciento noventa y dos punto ciento sesenta y ocho punto uno punto treinta y seis",
        ),
    ],
)
def test_to_spoken(text: str, spoken: str) -> None:
    assert to_spoken(text) == spoken
