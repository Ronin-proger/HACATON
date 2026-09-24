// Triplanar terrain (Three.js / ShaderMaterial onMeshStandardMaterial.onBeforeCompile)
// Pack: tAlbedo, tNormal, tRough — all RepeatWrapping.

const TriplanarChunks = {
  pars: /* glsl */ `
    uniform float uTile;
    vec3 triWeights(vec3 n) {
      vec3 w = pow(abs(n), vec3(4.0));
      return w / (w.x + w.y + w.z);
    }
    vec4 triAlbedo(sampler2D map, vec3 p, vec3 n, float tile) {
      vec3 w = triWeights(n);
      vec4 x = texture2D(map, p.zy * tile);
      vec4 y = texture2D(map, p.xz * tile);
      vec4 z = texture2D(map, p.xy * tile);
      return x * w.x + y * w.y + z * w.z;
    }
  `,
  color: /* glsl */ `
    vec3 wp = (modelMatrix * vec4(transformed, 1.0)).xyz;
    vec3 wn = normalize(mat3(modelMatrix) * objectNormal);
    diffuseColor.rgb *= triAlbedo(map, wp, wn, uTile).rgb;
  `,
};

export default TriplanarChunks;
