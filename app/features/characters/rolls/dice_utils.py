import random


def ability_modifier(score: int) -> int:
    """Standard D&D 5e ability modifier: floor((score - 10) / 2)."""
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    """
    Standard D&D 5e proficiency bonus by character level (1-20).

    +2 at levels 1-4, +3 at 5-8, +4 at 9-12, +5 at 13-16, +6 at 17-20.
    """
    return 2 + (max(level, 1) - 1) // 4


def roll_d20() -> int:
    return random.randint(1, 20)


def roll_dice(dice_expression: str) -> int:
    """
    Roll a dice expression like '1d8', '2d6', or a flat modifier like '3'.

    Supports a single 'NdM' term optionally followed by '+K'/'-K', e.g.
    '2d6+3'. Falls back to 0 for an empty/unparseable expression rather than
    raising, since damage_dice is a free-text field that may be blank.
    """
    expression = (dice_expression or "").strip().lower().replace(" ", "")
    if not expression:
        return 0

    modifier = 0
    dice_part = expression
    for sep in ("+", "-"):
        if sep in expression[1:]:  # avoid splitting a leading sign
            idx = expression.index(sep, 1)
            dice_part = expression[:idx]
            try:
                modifier = int(expression[idx:])
            except ValueError:
                modifier = 0
            break

    if "d" not in dice_part:
        try:
            return int(dice_part) + modifier
        except ValueError:
            return 0

    count_str, sides_str = dice_part.split("d", 1)
    try:
        count = int(count_str) if count_str else 1
        sides = int(sides_str)
    except ValueError:
        return 0

    if count <= 0 or sides <= 0:
        return modifier

    total = sum(random.randint(1, sides) for _ in range(count))
    return total + modifier
