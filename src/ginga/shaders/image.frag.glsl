#version 330
// Media wallpaper: one picture placed on the canvas, sampled in canvas pixel
// space so every monitor shows its own slice of the same image.
// Video frames arrive as YUV planes and are converted here (cheaper than on
// the CPU); rows may be padded, so each plane has its own horizontal scale.

uniform vec2      u_origin;      // this monitor's top-left inside the canvas, px
uniform vec2      u_resolution;  // this monitor's size in px
uniform vec4      u_rect;        // where the media is drawn: x, y, w, h in canvas px

uniform int       u_mode;        // 0 = RGB, 1 = YUV 4:2:0 planar, 2 = NV12
uniform sampler2D u_plane0;      // RGB, or Y
uniform sampler2D u_plane1;      // U (planar) or interleaved UV (NV12)
uniform sampler2D u_plane2;      // V (planar)
uniform vec2      u_luma_scale;    // visible width / padded width
uniform vec2      u_chroma_scale;
uniform mat3      u_yuv;         // rgb = u_yuv * (yuv - u_yuv_offset)
uniform vec3      u_yuv_offset;

in vec2 v_uv;
out vec4 f_color;

vec3 sample_media(vec2 uv) {
    if (u_mode == 0) {
        return texture(u_plane0, uv).rgb;
    }
    float y = texture(u_plane0, uv * u_luma_scale).r;
    vec2 c = u_mode == 1
        ? vec2(texture(u_plane1, uv * u_chroma_scale).r, texture(u_plane2, uv * u_chroma_scale).r)
        : texture(u_plane1, uv * u_chroma_scale).rg;
    return clamp(u_yuv * (vec3(y, c) - u_yuv_offset), 0.0, 1.0);
}

void main() {
    vec2 local = v_uv * u_resolution;
    vec2 px = vec2(u_origin.x + local.x, u_origin.y + (u_resolution.y - local.y));
    vec2 uv = (px - u_rect.xy) / u_rect.zw;
    if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) {
        f_color = vec4(0.0, 0.0, 0.0, 1.0);  // "fit" bars
        return;
    }
    f_color = vec4(sample_media(uv), 1.0);
}
