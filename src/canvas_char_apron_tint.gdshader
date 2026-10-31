// 待机回收站 · 店员围裙染色
// 用途：把店员图里的白色围裙染成所属 AI 的代表色，同一家 AI 的员工一眼认得出来。
// 目标：Compatibility 渲染器（网页导出），每像素 1 次采样，无分支。
shader_type canvas_item;

group_uniforms apron;
/** 所属 AI 的代表色 */
uniform vec4 tint_color : source_color = vec4(1.0);
/** 最暗通道高于这个值才算“白色”（围裙的阴影也要算进去） */
uniform float white_min : hint_range(0.0, 1.0) = 0.58;
/** 渐变宽度，避免染色边缘生硬 */
uniform float white_soft : hint_range(0.0, 0.5) = 0.16;
/** 颜色差（饱和度近似值）低于这个值才算“没有颜色” */
uniform float gray_max : hint_range(0.0, 0.5) = 0.10;
group_uniforms;

const float SHADE_BASE = 0.45;   // 染色后保留原来明暗：暗部不低于这个比例
const float SHADE_GAIN = 0.6;

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	float brightest = max(c.r, max(c.g, c.b));
	float darkest = min(c.r, min(c.g, c.b));
	// 越接近“又亮又没颜色”，权重越接近 1
	float whiteness = smoothstep(white_min, white_min + white_soft, darkest)
		* (1.0 - smoothstep(gray_max * 0.6, gray_max * 1.6, brightest - darkest));
	vec3 dyed = tint_color.rgb * (SHADE_BASE + SHADE_GAIN * brightest);
	COLOR = vec4(mix(c.rgb, dyed, whiteness), c.a);
}
