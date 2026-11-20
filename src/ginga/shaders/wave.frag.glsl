#version 330
// Procedural "light wave" wallpaper.
// Everything is computed in canvas pixel space so that multiple monitors,
// each rendering its own slice, form one seamless image.

uniform float u_time;
uniform vec2  u_canvas;      // canvas size in px
uniform vec2  u_origin;      // this monitor's top-left inside the canvas, px
uniform vec2  u_resolution;  // this monitor's size in px
uniform float u_speed;
uniform float u_amplitude;
uniform float u_glow;
uniform float u_spikes;

// "Modo berimbau": everything audio-driven is scaled by u_audio, so 0.0
// renders exactly the idle animation and the switch between them is smooth.
uniform float     u_audio;     // 0 = idle animation, 1 = fully audio-driven
uniform float     u_bass;      // 0..1, swells the wave
uniform float     u_level;     // 0..1, pulses the glow
uniform sampler2D u_spectrum;  // N x 1 bands across the canvas, bass on the left

in vec2 v_uv;
out vec4 f_color;

const float TAU = 6.2831853;

float hash(float n) { return fract(sin(n * 127.1) * 43758.5453); }

float noise(float x) {
    float i = floor(x);
    float f = fract(x);
    return mix(hash(i), hash(i + 1.0), f * f * (3.0 - 2.0 * f));
}

vec3 hsv2rgb(float h, float s, float v) {
    vec3 k = clamp(abs(fract(h + vec3(0.0, 2.0, 1.0) / 3.0) * 6.0 - 3.0) - 1.0, 0.0, 1.0);
    return v * mix(vec3(1.0), k, s);
}

// Wave height (in units of canvas height) at horizontal position u in [0, 1].
float wave(float u, float t) {
    float breathe = 0.75 + 0.25 * sin(t * 0.35 + u * 3.0);
    float y = 0.05 * sin(u * TAU * 3.5 - t * 0.6)
            + 0.012 * sin(u * TAU * 7.0 + t * 0.9)
            + 0.008 * sin(u * TAU * 1.3 + t * 0.25);
    return y * breathe * u_amplitude * (1.0 + 1.6 * u_bass * u_audio);
}

void main() {
    float t = u_time * u_speed;

    // Pixel position in canvas space (y grows downward, like Windows).
    vec2 local = v_uv * u_resolution;
    vec2 px = vec2(u_origin.x + local.x, u_origin.y + (u_resolution.y - local.y));

    float h = u_canvas.y;
    float u = px.x / u_canvas.x;
    float y = (px.y - 0.5 * h) / h;            // -0.5 .. 0.5 around the middle
    float d = abs(y - wave(u, t));             // distance to the curve

    // Rainbow along the canvas, slowly drifting.
    float hue = fract(0.98 - u * 0.92 + t * 0.01);
    vec3 color = hsv2rgb(hue, 0.85, 1.0);

    // Bright thin core + soft glow.
    float core = smoothstep(0.0022, 0.0, d);
    float glow = exp(-d * 40.0) * 0.7 * u_glow * (1.0 + 0.9 * u_level * u_audio);

    // Vertical "sound" spikes: 2px columns with flickering heights.
    float column = floor(px.x / 2.0);
    float tf = t * 10.0;
    float flicker = mix(hash(column + floor(tf) * 17.0),
                        hash(column + (floor(tf) + 1.0) * 17.0),
                        smoothstep(0.0, 1.0, fract(tf)));
    float envelope = 0.35 + 0.65 * noise(u * 14.0 + t * 0.3);
    float spikeLen = 0.17 * pow(flicker, 3.0) * envelope;
    // Audio: each column shows its frequency band; a little flicker keeps texture.
    float band = texture(u_spectrum, vec2(u, 0.5)).r;
    float audioLen = 0.24 * pow(band, 1.4) * (0.55 + 0.45 * flicker);
    spikeLen = mix(spikeLen, audioLen, u_audio);
    float spike = spikeLen > 0.0 ? pow(clamp(1.0 - d / spikeLen, 0.0, 1.0), 2.0) : 0.0;
    spike *= 0.75 * u_spikes;

    vec3 rgb = color * (glow + spike) + mix(color, vec3(1.0), 0.65) * core;
    rgb = 1.0 - exp(-rgb * 1.6);               // soft tone mapping
    f_color = vec4(rgb, 1.0);
}
