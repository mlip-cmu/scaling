"""A shared Altair theme for the charts (needs `altair` in the project that uses it)."""

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE, INK, INK_2, MUTED, GRID, AXIS = (
    "#fcfcfb",
    "#0b0b0b",
    "#52514e",
    "#898781",
    "#e1e0d9",
    "#c3c2b7",
)
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def enable() -> None:
    import altair as alt

    @alt.theme.register("photos", enable=True)
    def _theme() -> alt.theme.ThemeConfig:
        axis = {
            "gridColor": GRID,
            "gridWidth": 1,
            "domainColor": AXIS,
            "tickColor": AXIS,
            "labelColor": MUTED,
            "titleColor": INK_2,
            "labelFont": FONT,
            "titleFont": FONT,
            "titleFontWeight": "normal",
            "labelFontSize": 11,
            "titleFontSize": 12,
        }
        return {
            "config": {
                "background": SURFACE,
                "font": FONT,
                "view": {"stroke": None},
                "axis": axis,
                "axisX": {"grid": False},
                "legend": {
                    "labelColor": INK_2,
                    "titleColor": INK_2,
                    "labelFont": FONT,
                    "titleFont": FONT,
                    "orient": "top",
                    "titleFontWeight": "normal",
                },
                "title": {
                    "color": INK,
                    "font": FONT,
                    "fontWeight": 600,
                    "fontSize": 14,
                    "anchor": "start",
                    "subtitleColor": INK_2,
                },
                "range": {"category": SERIES},
                "line": {"strokeWidth": 2, "strokeCap": "round", "strokeJoin": "round"},
                "point": {"size": 64, "filled": True, "stroke": SURFACE, "strokeWidth": 2},
                "bar": {"cornerRadiusEnd": 4},
                "area": {"opacity": 0.1},
            }
        }
