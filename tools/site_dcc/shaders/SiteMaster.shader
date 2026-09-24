Shader "StroySync/SiteMaster"
{
    Properties
    {
        _Albedo ("Albedo", 2D) = "white" {}
        _ORM ("ORM (R rough G metal B AO)", 2D) = "white" {}
        _Normal ("Normal (OpenGL)", 2D) = "bump" {}
        _Height ("Displacement", 2D) = "gray" {}
        _Tile ("Tile", Float) = 0.18
        _BlendPow ("Triplanar sharpness", Float) = 4
        _Parallax ("Parallax", Range(0, 0.08)) = 0.012
        _ClearCoat ("Clear coat", Range(0, 1)) = 0
        _CoatRough ("Coat roughness", Range(0, 1)) = 0.35
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            Name "Forward"
            Tags { "LightMode"="UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_Albedo); SAMPLER(sampler_Albedo);
            TEXTURE2D(_ORM);    SAMPLER(sampler_ORM);
            TEXTURE2D(_Normal); SAMPLER(sampler_Normal);
            TEXTURE2D(_Height); SAMPLER(sampler_Height);
            float _Tile, _BlendPow, _Parallax, _ClearCoat, _CoatRough;

            struct A { float4 pos : POSITION; float3 nrm : NORMAL; float4 col : COLOR; };
            struct V { float4 pos : SV_POSITION; float3 wpos : TEXCOORD0; float3 wnrm : TEXCOORD1; float4 col : COLOR; };

            V vert(A v)
            {
                V o;
                o.wpos = TransformObjectToWorld(v.pos.xyz);
                o.wnrm = TransformObjectToWorldNormal(v.nrm);
                o.col = v.col;
                o.pos = TransformWorldToHClip(o.wpos);
                return o;
            }

            float3 triW(float3 n)
            {
                float3 w = pow(abs(n), _BlendPow);
                return w / max(w.x + w.y + w.z, 1e-5);
            }

            float4 tri(TEXTURE2D(tex), SAMPLER(s), float3 p, float3 n)
            {
                float3 w = triW(n);
                return SAMPLE_TEXTURE2D(tex, s, p.zy * _Tile) * w.x
                     + SAMPLE_TEXTURE2D(tex, s, p.xz * _Tile) * w.y
                     + SAMPLE_TEXTURE2D(tex, s, p.xy * _Tile) * w.z;
            }

            half4 frag(V i) : SV_Target
            {
                float3 n = normalize(i.wnrm);
                float h = tri(_Height, sampler_Height, i.wpos, n).r - 0.5;
                float3 p = i.wpos + n * h * _Parallax;
                float3 albedo = tri(_Albedo, sampler_Albedo, p, n).rgb;
                float3 orm = tri(_ORM, sampler_ORM, p, n).rgb;
                float3 nn = tri(_Normal, sampler_Normal, p, n).xyz * 2 - 1;
                n = normalize(n + nn * 0.35);

                Light light = GetMainLight();
                float ndl = saturate(dot(n, light.direction));
                float3 spec = light.color * pow(saturate(dot(n, normalize(light.direction + GetWorldSpaceNormalizeViewDir(i.wpos)))), lerp(8, 64, 1 - orm.r));
                float3 coat = _ClearCoat * spec * (1 - orm.r) * (1 - _CoatRough);
                float3 col = albedo * (ndl * light.color + 0.18) * orm.b + spec * orm.g + coat;
                col = lerp(col, col * float3(0.85, 0.78, 0.62), i.col.r);
                return half4(col, 1);
            }
            ENDHLSL
        }
    }
}
