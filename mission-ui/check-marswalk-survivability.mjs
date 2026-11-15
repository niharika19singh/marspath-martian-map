import assert from 'node:assert/strict';
import { computeClientMarswalkSurvivability } from './src/engine.js';
import { AUTHENTIC_NASA_SURFACE_IMAGES } from './src/surface_imagery.js';

console.log('🧪 Starting Marswalk Survivability & Surface Imagery Verification...\n');

// 1. Nominal flat terrain test
const nominal = computeClientMarswalkSurvivability({
  maxSlopeDeg: 3.5,
  averageRoughness: 0.15,
  durationHours: 1.2,
  maxEvaHours: 8.0,
  bufferMinutes: 120.0,
  themisTiu: 380.0,
  isSpeActive: false,
  coordinates: [[77.44, 18.44]],
});

console.log('1. Nominal Walkability Score:', nominal.score, nominal.category);
assert.ok(nominal.score >= 80, 'Nominal terrain must have optimal score >= 80');
assert.equal(nominal.category, 'OPTIMAL');
assert.equal(nominal.mobility_exertion_penalty, 0.0);
assert.equal(nominal.radiation_exposure_penalty, 0.0);

// 2. High slope exertion test (>12 degrees)
const steep = computeClientMarswalkSurvivability({
  maxSlopeDeg: 13.5,
  averageRoughness: 0.45,
  durationHours: 3.5,
  maxEvaHours: 8.0,
  bufferMinutes: 60.0,
  themisTiu: 320.0,
  isSpeActive: false,
  coordinates: [[77.44, 18.44]],
});

console.log('2. Steep Terrain Score:', steep.score, steep.category);
assert.ok(steep.mobility_exertion_penalty > 18.0, 'Slope > 12° must incur steep penalty');
assert.ok(steep.score < nominal.score, 'Steep terrain must lower score');

// 3. Solar Particle Event (SPE) without shelter
const speUnsheltered = computeClientMarswalkSurvivability({
  maxSlopeDeg: 3.5,
  averageRoughness: 0.15,
  durationHours: 1.2,
  maxEvaHours: 8.0,
  bufferMinutes: 120.0,
  themisTiu: 380.0,
  isSpeActive: true,
  coordinates: [[77.10, 18.10]], // Far from any shelter
});

console.log('3. SPE Unsheltered Score:', speUnsheltered.score, speUnsheltered.category);
assert.equal(speUnsheltered.radiation_exposure_penalty, 32.0, 'Unsheltered SPE must apply 32 pt penalty');
assert.equal(speUnsheltered.topographic_shelter_bonus, 0.0);

// 4. Solar Particle Event (SPE) near Séítah Swale shelter (77.440°E, 18.440°N)
const speSheltered = computeClientMarswalkSurvivability({
  maxSlopeDeg: 3.5,
  averageRoughness: 0.15,
  durationHours: 1.2,
  maxEvaHours: 8.0,
  bufferMinutes: 120.0,
  themisTiu: 380.0,
  isSpeActive: true,
  coordinates: [[77.4405, 18.4402]], // ~30m from shelter
});

console.log('4. SPE Sheltered Score:', speSheltered.score, speSheltered.category);
assert.equal(speSheltered.radiation_exposure_penalty, 8.0, 'Near shelter SPE penalty mitigated to 8.0');
assert.ok(speSheltered.topographic_shelter_bonus > 7.0, 'Near shelter must receive bonus points');
assert.equal(speSheltered.recommended_shelter_id, 'shelter_seitah_swale');

// 5. Authentic NASA Surface POV Catalogue Verification
console.log('5. NASA Surface POV Catalogue:', AUTHENTIC_NASA_SURFACE_IMAGES.length, 'images');
assert.equal(AUTHENTIC_NASA_SURFACE_IMAGES.length, 5, 'Must have 5 authentic Perseverance surface photos');
const ids = AUTHENTIC_NASA_SURFACE_IMAGES.map(img => img.nasa_id);
assert.ok(ids.includes('PIA24487'), 'Octavia Butler landing site panorama must exist');
assert.ok(ids.includes('PIA24836'), 'Kodiak Butte cross-bedding must exist');
assert.ok(ids.includes('PIA25439'), 'Hawksbill Gap delta mudstone must exist');
assert.ok(ids.includes('PIA24839'), 'South Séítah olivine cumulate must exist');
assert.ok(ids.includes('PIA25828'), 'Belva impact crater mosaic must exist');

for (const img of AUTHENTIC_NASA_SURFACE_IMAGES) {
  assert.ok(img.photojournal_url.startsWith('https://photojournal.jpl.nasa.gov/catalog/'), 'Valid JPL Photojournal URL');
  assert.ok(img.sol > 0, 'Valid Perseverance Sol');
  assert.ok(img.lat > 18.0 && img.lat < 19.0, 'Jezero latitude range');
  assert.ok(img.lon > 77.0 && img.lon < 78.0, 'Jezero longitude range');
}

console.log('\n🎉 ALL MARSWALK SURVIVABILITY & SURFACE POV CLIENT CHECKS PASSED!');
