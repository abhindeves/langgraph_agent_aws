import ast
import operator as op

_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Mod: op.mod,
}


def _eval_ast(node):
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.BinOp):
        return _OPERATORS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    elif isinstance(node, ast.UnaryOp):
        return _OPERATORS[type(node.op)](_eval_ast(node.operand))
    raise TypeError(f"Unsupported math operator: {type(node).__name__}")


def calculator(expression: str) -> str:
    """Calculate the result of a mathematical expression.

    Supports +, -, *, /, %, **, parentheses, and decimal operations.
    Examples:
        - "42 * 3 + 15"
        - "(120 / 4) ** 2"
        - "250 * 0.18"
    Args:
        expression: The mathematical expression string to calculate.
    """
    try:
        cleaned = expression.replace("^", "**")
        tree = ast.parse(cleaned, mode="eval")
        return str(_eval_ast(tree.body))
    except Exception as e:
        return f"Error evaluating expression: {e}"
