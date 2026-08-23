from fastapi.templating import Jinja2Templates

def _inr_format(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    int_part, _, dec = f"{value:.2f}".partition(".")
    groups = []
    int_str = int_part
    if len(int_str) <= 3:
        groups = [int_str]
    else:
        groups = [int_str[-3:]]
        int_str = int_str[:-3]
        while int_str:
            groups.insert(0, int_str[-2:])
            int_str = int_str[:-2]
    return ",".join(groups)

templates = Jinja2Templates(directory="templates")
templates.env.filters["inr"] = _inr_format