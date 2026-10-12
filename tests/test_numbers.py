from kwota.numbers import find_quantities


def labels(text):
    return [q.label() for q in find_quantities(text)]


def test_english_words_and_units():
    assert labels("three lengths of pipe and four elbows") == ["3 length", "4"]
    assert labels("twelve point five metres") == ["12.5 m"]
    assert labels("one hundred and twenty pieces") == ["120 pc"]
    assert labels("two and a half bags of cement") == ["2.5 bag"]


def test_digits_and_k():
    assert labels("15 cartons, 3 bag cement, 15k") == ["15 carton", "3 bag", "15000"]


def test_local_counting_words():
    assert labels("eeji trip sand") == ["2 trip"]      # Yoruba
    assert labels("buhu biyu cement, biyar bag") == ["2", "5 bag"]  # Hausa
    assert labels("abuo bucket") == ["2 bucket"]       # Igbo


def test_dimensions_become_area():
    assert labels("the room na twelve by ten feet") == ["120 sqft"]
    assert labels("floor na 20 square metres") == ["20 sqm"]


def test_pipe_sizes_are_not_quantities():
    assert labels("three lengths of half inch pipe, one inch pipe two lengths") == ["3 length", "2 length"]


def test_a_bag():
    assert labels("give me a bag of cement") == ["1 bag"]


def test_thirty_vs_thirteen_stay_apart():
    assert labels("No be thirty, thirteen lengths.") == ["30", "13 length"]
    assert labels("two three bags") == ["2", "3 bag"]
