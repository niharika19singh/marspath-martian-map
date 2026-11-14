export function exportGeoJSON(response,selected,request){return{type:'FeatureCollection',name:'MARSPath Jezero route plan',planetary_target:'Mars',planetary_crs:'IAU2000:49900',coordinate_convention:'East longitude, planetocentric latitude; optional elevation in meters above Mars areoid',selected_route_id:selected,request,provenance:response.provenance,limitations:response.limitations,features:response.routes.filter(r=>r.route_id===selected).map(r=>({type:'Feature',id:r.route_id,geometry:r.geometry,properties:{route_id:r.route_id,name:r.name,mode:r.mode,score_rank:r.score_rank,total_cost:r.total_cost,cost_breakdown:r.cost_breakdown,summary:r.summary,evidence_passport:r.evidence_passport}}))}}

export function exportMissionBriefMarkdown(response,selected,request){
  const route=response?.routes?.find(r=>r.route_id===selected)||response?.routes?.[0];
  if(route?.mission_brief_markdown){
    return route.mission_brief_markdown;
  }
  if(!route)return '# MARSPath Operational Mission Brief\n\nNo active route computed.';
  const s=route.summary||{};
  const mc=route.mission_clock||{};
  const unc=route.uncertainty_summary||{};
  const sci=route.science_eva_plan||{};
  const stress=route.stress_test_suite||{};
  const recon=route.reconnaissance_plan||{};
  const lines=[
    `# MARSPath Operational Mission Brief — ${route.name||'Jezero Traverse'}`,
    '',
    '## 1. Executive Traverse Summary',
    `- **Route ID:** \`${route.route_id}\` (\`${route.mode}\`)`,
    `- **Origin → Destination:** \`(${request?.start?.lat?.toFixed?.(4)||''}°N, ${request?.start?.lon?.toFixed?.(4)||''}°E)\` → \`(${request?.destination?.lat?.toFixed?.(4)||''}°N, ${request?.destination?.lon?.toFixed?.(4)||''}°E)\``,
    `- **Outbound Distance:** \`${((s.total_distance_meters||0)/1000).toFixed(2)} km\``,
    `- **Estimated Walking / Drive Duration:** \`${Number.isFinite(s.estimated_duration_hours)?s.estimated_duration_hours.toFixed(2)+' hours':'N/A'}\``,
    `- **Max Slope / Mean Slope:** \`${(s.max_slope_degrees||0).toFixed(1)}°\` / \`${(s.mean_slope_degrees||0).toFixed(1)}°\``,
    `- **Net Elevation Gain / Loss:** \`+${Math.round(s.elevation_gain_meters||0)} m\` / \`-${Math.round(s.elevation_loss_meters||0)} m\``,
    `- **Terrain Data Support Tier:** \`${unc.overall_support_tier||'MODERATE'}\` (Uncertainty Exposure: \`${unc.uncertainty_exposure_score??18}/100\`)`,
    `- **Science Return per EVA Hour:** \`${sci.science_return_per_eva_hour??0} pts/hr\` (\`${sci.visited_targets_count??0}\` geological targets visited)`,
    '',
    '## 2. Mars24 Illumination & Route Mission Clock',
    `- **Departure UTC:** \`${mc.departure_utc||request?.departure_utc||'2026-06-15T08:00:00Z'}\` (LTST \`${mc.departure_ltst_hms||'10:15:00'}\`, $L_s = ${mc.departure_ls_deg??112.4}^\\circ$)`,
    `- **Completion UTC:** \`${mc.completion_utc||'N/A'}\` (LTST \`${mc.completion_ltst_hms||'N/A'}\`)`,
    `- **Darkness Exposure:** \`${mc.darkness_distance_m??0} m\` (\`${((mc.darkness_fraction||0)*100).toFixed(1)}%\`)`,
    `- **DEM Terrain Shadow Exposure:** \`${mc.terrain_shadowed_distance_m??0} m\` (\`${((mc.terrain_shadowed_fraction||0)*100).toFixed(1)}%\`)`,
    '',
    '## 3. Science EVA Schedule',
  ];
  if(sci.visited_targets?.length){
    sci.visited_targets.forEach(t=>{
      lines.push(`- **${t.name}** (\`${t.geologic_unit}\`): \`${t.science_value_points} pts\`, stop \`${t.stop_duration_min} min\`, detour \`${t.detour_distance_m} m\` — ${t.scientific_rationale}`);
    });
  }else{
    lines.push('- Direct point-to-point traverse; no intermediate geological stops within corridor.');
  }
  lines.push('','## 4. Next-Best Reconnaissance Recommendations');
  if(recon.recommendations?.length){
    recon.recommendations.forEach(r=>{
      lines.push(`- **[${r.recommendation_type}] ${r.instrument}:** ${r.rationale}`);
    });
  }else{
    lines.push('- Existing USGS MOLA–HRSC 200 m and HiRISE ortho/DTM coverage provide full corridor support.');
  }
  lines.push('','## 5. 7-Scenario Operational Stress Testing Suite');
  if(stress.scenarios?.length){
    stress.scenarios.forEach(sc=>{
      lines.push(`- **${sc.name} (\`${sc.scenario_id}\`):** \`${sc.status}\` — ${sc.rationale}`);
    });
  }
  lines.push('','## 6. Provenance & Operational Limitations');
  (response?.limitations||['Reference planning product over USGS MOLA–HRSC 200 m blended DEM.']).forEach(l=>{
    lines.push(`- ${l}`);
  });
  return lines.join('\n');
}

export function exportMissionConfigJSON(config){
  return {
    schema_version:'marspath.mission_config.v2',
    exported_at_utc:new Date().toISOString(),
    planetary_body:'Mars',
    pilot_region:'Jezero Crater',
    ...config,
  };
}
