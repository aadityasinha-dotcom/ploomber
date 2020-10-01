import pytest
from ploomber.static_analysis.python import PythonNotebookExtractor
from ploomber.static_analysis.r import RNotebookExtractor
from ploomber.static_analysis.sql import SQLExtractor
from ploomber.static_analysis.string import StringExtractor
from ploomber.products import (PostgresRelation, SQLiteRelation,
                               GenericSQLRelation, SQLRelation)

cell_case_1 = """
upstream = {'some_key': 'some_value'}
""", ['some_key']

cell_case_2 = """
upstream = {'a': None, 'b': None}
product, some_variable = None, None

if upstream:
    pass

for i in range(10):
    print(i)

if True:
    upstream = {'x': None, 'y': None}
""", ['a', 'b']

case_error_1 = "some_variable = 1"
case_error_2 = """
upstreammm = {'a': 1}
"""
case_error_3 = "upstream = 1"


@pytest.mark.parametrize('code', [case_error_1, case_error_2, case_error_3])
def test_error_from_code_cell(code):
    extractor = PythonNotebookExtractor(parameters_cell=code)

    with pytest.raises(ValueError):
        extractor.extract_upstream()


@pytest.mark.parametrize('code, class_', [
    ['SELECT * FROM table', SQLExtractor],
    ['product = None', PythonNotebookExtractor],
    ['', PythonNotebookExtractor],
])
def test_error_message_when_missing_product(code, class_):
    extractor = class_(code)

    with pytest.raises(ValueError) as excinfo:
        extractor.extract_product()

    assert str(excinfo.value) == ("Couldn't extract 'product' from code:\n" +
                                  code)


@pytest.mark.parametrize('code, class_', [
    ['{% set product = None %}', SQLExtractor],
    ['{% set product = 1 %}', SQLExtractor],
    ['{% set product = "a" %}', SQLExtractor],
    ['{% set product = ["schema", "name", "table"] %}', SQLExtractor],
])
def test_error_when_sql_product_is_invalid(code, class_):
    extractor = class_(code)

    with pytest.raises(ValueError) as excinfo:
        extractor.extract_product()

    expected = ("Found a variable named 'product' in "
                "code: {} but it does not appear to "
                "be a valid SQL product, verify it ".format(code))
    assert str(excinfo.value) == expected


@pytest.mark.parametrize('extractor', [
    PythonNotebookExtractor(
        "upstream = ['a', 'b', 'c']\nproduct={'d': 'path/d.csv'}"),
    PythonNotebookExtractor(
        "upstream = ['a', 'b', 'c']\n\nproduct={'d': 'path/d.csv'}"),
    PythonNotebookExtractor(
        "product={'d': 'path/d.csv'}\n\nupstream = ['a', 'b', 'c']\n\n"),
    PythonNotebookExtractor(
        "upstream = ['a', 'b', 'c']\nproduct={'d': 'path/d.csv'}\nfn(x)\n"),
    PythonNotebookExtractor(
        "upstream = ['a', 'b', 'c']\nproduct={'d': 'path/d.csv'}\nx\n"),
    RNotebookExtractor(
        "upstream <- list('a', 'b', 'c')\n\nproduct <- list(d='path/d.csv')"),
    RNotebookExtractor(
        "upstream = list('a', 'b', 'c')\n\nproduct = list(d='path/d.csv')"),
    RNotebookExtractor(
        "\nproduct <- list(d='path/d.csv')\n\nupstream <- list('a', 'b', 'c')"
    ),
])
def test_extract_variables(extractor):
    assert extractor.extract_upstream() == set(['a', 'b', 'c'])
    assert extractor.extract_product() == {'d': 'path/d.csv'}


def test_extract_upstream_sql():
    code = """CREATE TABLE {{product}} something AS
SELECT * FROM {{upstream['some_task']}}
JOIN {{upstream['another_task']}}
USING some_column
"""
    extractor = SQLExtractor(code)
    assert extractor.extract_upstream() == {'some_task', 'another_task'}


@pytest.mark.parametrize('code, expected', [cell_case_1, cell_case_2])
def test_infer_from_code_cell(code, expected):
    extractor = PythonNotebookExtractor(parameters_cell=code)
    inferred = extractor.extract_upstream()
    assert sorted(inferred) == sorted(expected)


@pytest.mark.parametrize('code, class_, schema, name, kind', [
    [
        '{% set product =  PostgresRelation(["s", "n", "table"]) %} some code',
        PostgresRelation, 's', 'n', 'table'
    ],
    [
        'simulating some code here {% set product =  SQLiteRelation(["s", "n", "view"]) %}',
        SQLiteRelation, 's', 'n', 'view'
    ],
    [
        '{% set product =  GenericSQLRelation(["s", "n", "table"]) %}',
        GenericSQLRelation, 's', 'n', 'table'
    ],
    [
        '{% set product =  SQLRelation(["s", "n", "view"]) %}', SQLRelation,
        's', 'n', 'view'
    ]
])
def test_extract_product_from_sql(code, class_, schema, name, kind):
    extracted = SQLExtractor(code).extract_product()
    assert isinstance(extracted, class_)
    assert extracted.name == name
    assert extracted.schema == schema
    assert extracted.kind == kind


@pytest.mark.parametrize('source, expected', [
    ['{{upstream["key"]}}', {'key'}],
    [
        '{{upstream["key"]}} - {{upstream["another_key"]}}',
        {'key', 'another_key'}
    ],
    ['{{hello}}', None],
])
def test_string_extractor(source, expected):
    assert StringExtractor(source).extract_upstream() == expected