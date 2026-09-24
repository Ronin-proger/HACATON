// StroySync terrain — object-space triplanar, OpenGL (Three.js / glTF).
// Sample albedo + packed ORM (R roughness, G metallic, B AO) + tangentless normal.

uniform sampler2D tAlbedo;
uniform sampler2D tORM;
uniform sampler2D tNormal;
uniform float uTile;
uniform float uBlendPow;

varying vec3 vWorldPos;
varying vec3 vWorldN;

vec3 triWeights(vec3 n) {
  vec3 w = pow(abs(n), vec3(uBlendPow));
  return w / max(w.x + w.y + w.z, 1e-5);
}

vec4 triSample(sampler2D map, vec3 p, vec3 n, float tile) {
  vec3 w = triWeights(n);
  vec4 x = texture2D(map, p.zy * tile);
  vec4 y = texture2D(map, p.xz * tile);
  vec4 z = texture2D(map, p.xy * tile);
  return x * w.x + y * w.y + z * w.z;
}

vec3 triNormal(sampler2D map, vec3 p, vec3 n, float tile) {
  vec3 w = triWeights(n);
  vec3 nx = texture2D(map, p.zy * tile).xyz * 2.0 - 1.0;
  vec3 ny = texture2D(map, p.xz * tile).xyz * 2.0 - 1.0;
  vec3 nz = texture2D(map, p.xy * tile).xyz * 2.0 - 1.0;
  nx = vec3(nx.zy, abs(n.x));
  ny = vec3(ny.xz, abs(n.y));
  nz = vec3(nz.xy, abs(n.z));
  return normalize(nx * w.x + ny * w.y + nz * w.z);
}

void applyTriplanar(inout vec3 albedo, inout float rough, inout float metal, inout float ao, inout vec3 nrm) {
  vec3 n = normalize(vWorldN);
  albedo = triSample(tAlbedo, vWorldPos, n, uTile).rgb;
  vec3 orm = triSample(tORM, vWorldPos, n, uTile).rgb;
  rough = orm.r;
  metal = orm.g;
  ao = orm.b;
  nrm = triNormal(tNormal, vWorldPos, n, uTile);
}
