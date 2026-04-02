
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_ColorGen

def hex_to_quantity(hex_color: str) -> Quantity_Color:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return Quantity_Color(r, g, b, Quantity_TOC_RGB)


def quantity_to_hex(c: Quantity_Color) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(round(c.Red() * 255)),
        int(round(c.Green() * 255)),
        int(round(c.Blue() * 255)),
    )


def _get_face_color(color_tool, face_label, face_shape, parent_label):
    q = Quantity_Color()
    if face_label is not None and not face_label.IsNull():
        if color_tool.GetColor_s(face_label, XCAFDoc_ColorSurf, q):
            return quantity_to_hex(q)
        if color_tool.GetColor_s(face_label, XCAFDoc_ColorGen, q):
            return quantity_to_hex(q)
    if color_tool.GetColor(face_shape, XCAFDoc_ColorSurf, q):
        return quantity_to_hex(q)
    if color_tool.GetColor(face_shape, XCAFDoc_ColorGen, q):
        return quantity_to_hex(q)
    if parent_label is not None and not parent_label.IsNull():
        if color_tool.GetColor_s(parent_label, XCAFDoc_ColorSurf, q):
            return quantity_to_hex(q)
        if color_tool.GetColor_s(parent_label, XCAFDoc_ColorGen, q):
            return quantity_to_hex(q)
    return None
