#ifndef SSRef
#define SSRef

// Screen-space reflections for SSR_Water.shadergraph.
//
// The ray is marched in world space from the water surface and every sample is
// projected with the camera's real view-projection matrix, so its depth can be
// compared directly with the scene's linear eye depth. Rays that leave the
// screen or hit nothing fall back to the reflection probe (sky) instead of a
// flat gray, which used to show up as per-pixel speckles on choppy water.

#define SSR_MAX_DISTANCE 300.0
#define SSR_REFINE_STEPS 5
#define SSR_EDGE_FADE 0.08
#define SSR_MIN_REFLECTION_Y 0.05

// ---------------------------------------------------------------------------
// Water surface normal
//
// The graph used to turn the wave noise into a normal with Normal From Height,
// which differentiates the height with ddx/ddy. Those derivatives are constant
// per 2x2 pixel quad, so the normal (and everything lit or reflected with it)
// came out as 2x2 blocks: the mosaic look in the middle distance. Here the
// same noise is differentiated analytically per pixel instead, and only the
// octaves that are finer than a pixel are faded out.
// ---------------------------------------------------------------------------

// Same hash as Shader Graph's Gradient Noise node with Hash Type "LegacyMod".
float WaterHashLegacyMod(float2 i)
{
	i = i % 289;
	float x = float(34 * i.x + 1) * i.x % 289 + i.y;
	x = (34 * x + 1) * x % 289;
	return frac(x / 41) * 2 - 1;
}

float2 WaterGradientDir(float2 p)
{
	float x = WaterHashLegacyMod(p);
	return normalize(float2(x - floor(x + 0.5), abs(x) - 0.5));
}

// Shader Graph's Gradient Noise (minus its +0.5 offset, which has no slope),
// returning its gradient with respect to p = UV * Scale.
float2 WaterGradientNoiseGrad(float2 p)
{
	float2 ip = floor(p);
	float2 fp = frac(p);

	float2 g00 = WaterGradientDir(ip);
	float2 g01 = WaterGradientDir(ip + float2(0, 1));
	float2 g10 = WaterGradientDir(ip + float2(1, 0));
	float2 g11 = WaterGradientDir(ip + float2(1, 1));

	float d00 = dot(g00, fp);
	float d01 = dot(g01, fp - float2(0, 1));
	float d10 = dot(g10, fp - float2(1, 0));
	float d11 = dot(g11, fp - float2(1, 1));

	float2 u = fp * fp * fp * (fp * (fp * 6 - 15) + 10);
	float2 du = 30 * fp * fp * (fp * (fp - 2) + 1);

	float k = d00 - d10 - d01 + d11;
	float2 grad = g00 + u.x * (g10 - g00) + u.y * (g01 - g00) + u.x * u.y * (g00 - g10 - g01 + g11);
	grad.x += du.x * (d10 - d00 + u.y * k);
	grad.y += du.y * (d01 - d00 + u.x * k);
	return grad;
}

// 1 while a noise cell spans more than ~2 pixels, 0 once it is down to ~1.
float WaterOctaveFade(float cellsPerPixel)
{
	return 1.0 - smoothstep(0.5, 1.0, cellsPerPixel);
}

// Height = weight * (GradientNoise(uvA) + GradientNoise(uvB)) / 2, with
// uvA/uvB = positionWS.xz * worldTiling * tilingA/B + offset (see WSUV_Water).
// Returns the perturbed world-space normal, matching Normal From Height's
// N - Strength * surfaceGradient.
void WaterNoiseNormal_float(float2 uvA, float2 uvB, float scale, float worldTiling, float tilingA, float tilingB, float weight, float strength, float3 positionWS, float3 normalWS, out float3 Out)
{
	float freqA = scale * worldTiling * tilingA; // noise cells per world unit
	float freqB = scale * worldTiling * tilingB;

	// World size of this pixel: geometric mean of the screen-space axes, so
	// grazing angles are not over-blurred by the long axis alone.
	float footprint = sqrt(length(ddx(positionWS)) * length(ddy(positionWS)));

	float2 gradA = WaterGradientNoiseGrad(uvA * scale) * freqA * WaterOctaveFade(footprint * freqA);
	float2 gradB = WaterGradientNoiseGrad(uvB * scale) * freqB * WaterOctaveFade(footprint * freqB);

	// Height gradient in world space (noise is projected on the XZ plane).
	float2 h = weight * 0.5 * (gradA + gradB);
	float3 N = normalize(normalWS);
	float3 grad = float3(h.x, 0, h.y);
	float3 surfGrad = grad - dot(grad, N) * N;
	Out = normalize(N - strength * surfGrad);
}

float SceneDepth(float2 UV)
{
	return LinearEyeDepth(SHADERGRAPH_SAMPLE_SCENE_DEPTH(UV), _ZBufferParams);
}

float3 SceneColor(float2 UV)
{
	return SHADERGRAPH_SAMPLE_SCENE_COLOR(UV);
}

// Projects a world position to the same normalized screen UV that Shader
// Graph's default Screen Position uses. Returns the linear eye depth in z
// (<= 0 when the point is behind the camera).
float3 WorldToScreenUVDepth(float3 positionWS)
{
	float4 positionCS = TransformWorldToHClip(positionWS);
	float w = positionCS.w;
	float2 ndc = positionCS.xy / max(abs(w), 1e-5);
	float2 uv;
	uv.x = ndc.x * 0.5 + 0.5;
	uv.y = ndc.y * _ProjectionParams.x * 0.5 + 0.5;
	return float3(uv, w);
}

bool IsOnScreen(float2 uv)
{
	return all(uv >= 0.0) && all(uv <= 1.0);
}

// 0 at the screen border, 1 once SSR_EDGE_FADE inside it.
float ScreenEdgeFade(float2 uv)
{
	float2 edge = min(uv, 1.0 - uv);
	return saturate(min(edge.x, edge.y) / SSR_EDGE_FADE);
}

// viewDir and _normal are world space; _normal must already be the perturbed
// water normal transformed out of tangent space.
void SSR_float(float3 viewDir, float stepSize, float4 screenPos, float samples, float thickness, float smoothness, float3 _normal, float3 _position, bool reconstructDepth, out float3 col)
{
	float3 V = normalize(viewDir);
	float3 N = normalize(_normal);
	float3 R = reflect(-V, N);

	// At grazing angles a tilted wave normal can send the reflected ray into
	// the water, where it would only find the sea floor behind the surface (and
	// the probe's ground color). In reality it bounces off the neighbouring
	// wave, so mirror it back up. Mirroring is continuous at R.y = 0, unlike a
	// clamp, which turned every such pixel into the same flat color.
	R.y = abs(R.y);

	// Fallback: sky / reflection probe in the same direction. Keep the lookup
	// slightly above the horizon so it never blends in the skybox ground.
	float3 envDir = normalize(float3(R.x, max(R.y, SSR_MIN_REFLECTION_Y), R.z));
	float3 H = normalize(V + envDir);
	float3 envCol = SHADERGRAPH_REFLECTION_PROBE(V, H, 0);
	col = envCol;

	int stepCount = max((int)samples, 1);
	float maxDist = min(SSR_MAX_DISTANCE, _ProjectionParams.z);
	float minStep = max(stepSize, 0.01);

	float prevT = 0.0;
	bool hit = false;
	float hitT = 0.0;

	UNITY_LOOP
	for (int i = 1; i <= stepCount; i++)
	{
		// Quadratic distribution: short steps near the surface for contact
		// detail, long ones further out to reach distant geometry.
		float f = (float)i / stepCount;
		float t = max(maxDist * f * f, prevT + minStep);

		float3 p = _position + R * t;
		float3 s = WorldToScreenUVDepth(p);
		if (s.z <= 0.0 || !IsOnScreen(s.xy))
			break;

		float sceneDepth = SceneDepth(s.xy);
		float delta = s.z - sceneDepth;
		// The ray is behind the depth buffer. Accept it only if it is within
		// the thickness of the surface (plus this step's length, since the
		// crossing lies somewhere inside the step); otherwise it passed behind
		// a foreground object and should keep going.
		if (delta > 0.0 && delta < thickness + (t - prevT))
		{
			hit = true;
			hitT = t;
			break;
		}
		prevT = t;
	}

	if (!hit)
		return;

	// Binary search between the last sample in front and the first behind.
	float lo = prevT;
	float hi = hitT;
	UNITY_UNROLL
	for (int j = 0; j < SSR_REFINE_STEPS; j++)
	{
		float mid = 0.5 * (lo + hi);
		float3 s = WorldToScreenUVDepth(_position + R * mid);
		if (s.z > SceneDepth(s.xy))
			hi = mid;
		else
			lo = mid;
	}

	float3 hitUV = WorldToScreenUVDepth(_position + R * hi);
	float3 hitCol = min(SceneColor(hitUV.xy), 5);

	float fade = ScreenEdgeFade(hitUV.xy) * (1.0 - smoothstep(0.7, 1.0, hi / maxDist));
	col = lerp(envCol, hitCol, fade);
}

#endif
