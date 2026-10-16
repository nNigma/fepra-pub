from tjbot.handlers.club import _strip_program_wrappers as strip


def test_strips_double_programma():
    assert strip("Программа:\n\nПрограмма:\n\nРАЗМИНКА\n- x") == "РАЗМИНКА\n- x"


def test_strips_view_and_edit_wrappers():
    src = "Текущая программа:\n\nПрограмма Universe на 2026-07-04:\n\n1. Су"
    assert strip(src) == "1. Су"


def test_strips_date_and_zala_headers():
    assert strip("Программа на 2026-07-06:\n\nРазминка:\n- x") == "Разминка:\n- x"
    assert strip("Программа зала на эту дату:\n\nWOD\n- x") == "WOD\n- x"


def test_clean_board_untouched():
    board = "РАЗМИНКА\n2 серии:\n- 1 мин кардио"
    assert strip(board) == board


def test_real_movement_line_not_stripped():
    # строка секции доски, не обёртка бота
    assert strip("Разминка:\n- 10 приседаний") == "Разминка:\n- 10 приседаний"


def test_english_wrappers():
    assert strip("Program:\n\nWOD\n- x") == "WOD\n- x"
    assert strip("Current program:\n\nProgram Universe for 2026-07-04:\n\nWOD") == "WOD"
