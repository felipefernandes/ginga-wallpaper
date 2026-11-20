#version 330
// Calibration guides drawn over the wave.
// Lines live in canvas space: they look continuous across monitors only when
// the calibration offsets match the physical arrangement. Horizontal lines
// reveal vertical misalignment; diagonals reveal horizontal (bezel) gaps too.

uniform vec2  u_origin;      // this monitor's top-left inside the canvas, px
uniform vec2  u_resolution;  // this monitor's size in px
uniform float u_selected;    // 1.0 on the monitor being moved

in vec2 v_uv;
out vec4 f_color;

const float SPACING = 60.0;       // px between horizontal lines
const float DIAG_SPACING = 240.0; // px between diagonal lines (measured along x)

// 1.0 on a ~width px line around every multiple of `spacing`, anti-aliased.
float lines(float coord, float spacing, float width) {
    float d = abs(mod(coord + spacing * 0.5, spacing) - spacing * 0.5);
    return 1.0 - smoothstep(width * 0.5, width * 0.5 + 1.0, d);
}

void main() {
    vec2 local = vec2(v_uv.x, 1.0 - v_uv.y) * u_resolution;  // y down, like Windows
    vec2 p = u_origin + local;

    bool major = abs(mod(p.y + SPACING * 2.5, SPACING * 5.0) - SPACING * 2.5) < 2.0;
    float h = lines(p.y, SPACING, major ? 3.0 : 1.0) * (major ? 0.85 : 0.4);
    float d1 = lines(p.x + p.y, DIAG_SPACING, 1.5);
    float d2 = lines(p.x - p.y, DIAG_SPACING, 1.5);
    float diag = max(d1, d2) * 0.45;

    // Border marks which monitor the arrows move.
    float edge = min(min(local.x, u_resolution.x - local.x), min(local.y, u_resolution.y - local.y));
    float border = 1.0 - smoothstep(5.0, 6.0, edge);

    vec3 guide = vec3(1.0);
    vec3 accent = mix(vec3(0.45), vec3(0.2, 0.95, 1.0), u_selected);
    float a = max(h, diag);
    vec3 color = mix(guide, accent, border);
    f_color = vec4(color, max(a, border * mix(0.5, 1.0, u_selected)));
}
