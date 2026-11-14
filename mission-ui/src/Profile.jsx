import React,{useMemo,useState,useRef}from'react';
import{M_PER_DEG}from'./terrain.js';
import Icon from'./Icons.jsx';

export default function Profile({route,onHover,expanded,onToggle,busy,activeProfileTab:externalTab,onSelectProfileTab}){
  const[at,setAt]=useState(null);
  const[localTab,setLocalTab]=useState('elevation');
  const activeTab=externalTab||localTab;
  const setTab=t=>{setLocalTab(t);onSelectProfileTab?.(t);};
  const drag=useRef(null),skipClick=useRef(false);

  const points=useMemo(()=>{
    if(!route)return[];
    let distance=0;
    const segments=route.evidence_passport?.segments;
    return route.geometry.coordinates.map((c,i,a)=>{
      const seg=segments?.[Math.max(0,i-1)];
      const fallbackZ=i===0?seg?.elevation_start_m:seg?.elevation_end_m;
      const z=Number.isFinite(c[2])?c[2]:Number.isFinite(fallbackZ)?fallbackZ:null;
      if(i){
        const p=a[i-1];
        const prevSeg=segments?.[i-1];
        const prevZ=Number.isFinite(p[2])?p[2]:Number.isFinite(prevSeg?.elevation_start_m)?prevSeg.elevation_start_m:null;
        distance+=Math.hypot((c[0]-p[0])*M_PER_DEG*Math.cos(c[1]*Math.PI/180),(c[1]-p[1])*M_PER_DEG,z!==null&&prevZ!==null?z-prevZ:0);
      }
      return{
        coordinate:c,
        distance,
        z,
        slope:Number.isFinite(seg?.slope_deg)?seg.slope_deg:null,
        roughness:Number.isFinite(seg?.roughness)?seg.roughness:null,
        support_tier:seg?.support_tier||'MODERATE'
      };
    });
  },[route]);

  const valid=points.filter(p=>p.z!==null);
  const min=valid.length?Math.min(...valid.map(p=>p.z)):0;
  const max=valid.length?Math.max(...valid.map(p=>p.z)):1;
  const range=Math.max(max-min,5);
  const total=points.at(-1)?.distance||1;
  const x=p=>64+p.distance/total*900;
  const y=p=>150-(p.z-min)/range*115;
  const hover=at===null?null:points[at];
  const color=s=>s===null?'#a0afa7':s<7?'#78d8a3':s<12?'#dfb879':'#cc8b79';

  let chunks=[],chunk=[];
  for(const p of points){
    if(p.z===null){if(chunk.length)chunks.push(chunk);chunk=[];}
    else chunk.push(p);
  }
  if(chunk.length)chunks.push(chunk);
  const spark=valid.map(p=>`${p.distance/total*180},${26-(p.z-min)/range*22}`).join(' ');

  const mc=route?.mission_clock;
  const unc=route?.uncertainty_summary;
  const sci=route?.science_eva_plan;
  const recon=route?.reconnaissance_plan;
  const pareto=route?.pareto_frontier;
  const stress=route?.stress_test_suite;
  const maxSlopeVal=route?.summary?.max_slope_deg??route?.summary?.max_slope_degrees;
  const avgSlopeVal=route?.summary?.average_slope_deg??route?.summary?.mean_slope_degrees;

  return (
    <section className={'terrain-drawer glass '+(expanded?'expanded':'')} aria-label="Terrain profile and operational mission analytics">
      <button
        className="profile-handle"
        onClick={()=>{if(skipClick.current){skipClick.current=false;return}onToggle()}}
        onPointerDown={e=>{drag.current=e.clientY;e.currentTarget.setPointerCapture(e.pointerId)}}
        onPointerUp={e=>{if(drag.current!==null&&Math.abs(e.clientY-drag.current)>22){skipClick.current=true;onToggle(e.clientY<drag.current)}drag.current=null}}
        aria-expanded={expanded}
        aria-controls="terrain-profile-chart"
      >
        <span className="profile-title">
          <span className="drawer-grip"/>
          Terrain &amp; Mission Analytics
          <small>{busy?'Computing…':route?'5-tab engineering & science workbench':'Generate a route to begin'}</small>
        </span>
        <svg className="sparkline" viewBox="0 0 180 32" aria-hidden="true">
          <polyline points={spark} fill="none" stroke="#d8b27e" strokeWidth="1.5"/>
        </svg>
        <span className="profile-mini-stat"><b>{Number.isFinite(maxSlopeVal)?Math.round(maxSlopeVal)+'°':'—'}</b><small>Max slope</small></span>
        <span className="profile-mini-stat"><b>{Number.isFinite(avgSlopeVal)?avgSlopeVal.toFixed(1)+'°':'—'}</b><small>Avg slope</small></span>
        <span className="profile-mini-stat"><b>{sci?.science_return_per_eva_hour?sci.science_return_per_eva_hour+' pts/h':Number.isFinite(route?.summary.elevation_gain_meters)?Math.round(route.summary.elevation_gain_meters)+' m':'—'}</b><small>{sci?'Science/EVA h':'Ascent'}</small></span>
        <span className="profile-mini-stat descent"><b>{stress?`${stress.scenarios_passed_count}/${stress.scenarios_evaluated_count} PASS`:Number.isFinite(route?.summary.elevation_loss_meters)?Math.round(route.summary.elevation_loss_meters)+' m':'—'}</b><small>{stress?'Stress Suite':'Descent'}</small></span>
        <span className={'profile-chevron '+(expanded?'open':'')}><Icon name="chevron"/></span>
      </button>

      <div className="profile-body" id="terrain-profile-chart" hidden={!expanded}>
        <div className="profile-tabs" role="tablist" aria-label="Mission analytics tabs" style={{display:'flex',gap:'6px',marginBottom:'10px',flexWrap:'wrap',borderBottom:'1px solid rgba(255,255,255,0.08)',paddingBottom:'8px'}}>
          {[
            ['elevation','1. Elevation & Slope'],
            ['clock','2. Route Mission Clock (Mars24)'],
            ['uncertainty','3. Uncertainty & Next-Best Recon'],
            ['science','4. Science Return & Pareto Frontier'],
            ['stress','5. 7-Scenario Stress Suite'],
          ].map(([id,label])=>(
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={activeTab===id}
              onClick={()=>setTab(id)}
              style={{
                background:activeTab===id?'rgba(92,255,176,0.16)':'rgba(255,255,255,0.04)',
                color:activeTab===id?'#9becbf':'#b9c8c4',
                border:activeTab===id?'1px solid rgba(92,255,176,0.45)':'1px solid rgba(255,255,255,0.08)',
                borderRadius:'8px',
                padding:'5px 11px',
                fontSize:'11.5px',
                fontWeight:activeTab===id?600:500,
                cursor:'pointer'
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {activeTab==='elevation'&&(
          valid.length?(
            <>
              <div className="profile-legend">
                <span><i style={{background:'#78d8a3'}}/>Below 7°</span>
                <span><i style={{background:'#dfb879'}}/>7–12°</span>
                <span><i style={{background:'#cc8b79'}}/>Above 12°</span>
                <span>Elevation above Mars areoid (200 m USGS MOLA–HRSC DEM)</span>
              </div>
              <div
                className="profile-chart"
                onPointerMove={e=>{
                  const rect=e.currentTarget.getBoundingClientRect();
                  const ratio=Math.max(0,Math.min(1,((e.clientX-rect.left)/rect.width*1000-64)/900));
                  const dist=ratio*total;
                  let index=0;
                  for(let i=1;i<points.length;i++)if(Math.abs(points[i].distance-dist)<Math.abs(points[index].distance-dist))index=i;
                  setAt(index);
                  onHover(points[index].coordinate);
                }}
                onPointerLeave={()=>{setAt(null);onHover(null)}}
              >
                <svg viewBox="0 0 1000 190" role="img" aria-label={`Measured elevation profile from ${min.toFixed(0)} to ${max.toFixed(0)} meters`} preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="profile-area" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#d8b27e" stopOpacity=".25"/>
                      <stop offset="100%" stopColor="#d8b27e" stopOpacity="0"/>
                    </linearGradient>
                  </defs>
                  {[35,92,150].map((yy,i)=>(
                    <g key={i}>
                      <line x1="64" x2="964" y1={yy} y2={yy} stroke="#ffffff0d"/>
                      <text x="2" y={yy+4}>{Math.round(max-(max-min)*i/2)} m</text>
                    </g>
                  ))}
                  {chunks.map((ps,i)=>(
                    <g key={i}>
                      <path d={`M ${x(ps[0])} 155 L ${ps.map(p=>`${x(p)} ${y(p)}`).join(' L ')} L ${x(ps.at(-1))} 155 Z`} fill="url(#profile-area)"/>
                      {ps.slice(1).map((p,k)=>(
                        <line key={k} x1={x(ps[k])} y1={y(ps[k])} x2={x(p)} y2={y(p)} stroke={color(p.slope)} strokeWidth="2" vectorEffect="non-scaling-stroke"/>
                      ))}
                    </g>
                  ))}
                  {[0,.25,.5,.75,1].map(n=>(
                    <text key={n} x={64+n*900} y="183" textAnchor="middle">{(n*total/1000).toFixed(2)} km</text>
                  ))}
                  {route?.turnaround && Number.isFinite(route.turnaround.turnaround_distance_m) && (
                    <g>
                      {(() => {
                        const tx = 64 + (Math.min(total, Math.max(0, route.turnaround.turnaround_distance_m)) / total) * 900;
                        const fill = route.turnaround.feasible_before_sunset ? '#ffb867' : '#ff6b6b';
                        return (
                          <>
                            <line x1={tx} x2={tx} y1="14" y2="158" stroke={fill} strokeWidth="2" strokeDasharray="4 3" />
                            <circle cx={tx} cy="16" r="4.5" fill={fill} stroke="#11161a" strokeWidth="1.5" />
                            <text x={Math.min(890, Math.max(85, tx))} y="12" fill={fill} fontSize="10" fontWeight="600" textAnchor="middle">
                              Turnaround {route.turnaround.turnaround_ltst_hms || ''}
                            </text>
                          </>
                        );
                      })()}
                    </g>
                  )}
                  {hover&&hover.z!==null&&(
                    <g>
                      <line x1={x(hover)} x2={x(hover)} y1="16" y2="157" stroke="#e1d4bb88" strokeDasharray="3 4"/>
                      <circle cx={x(hover)} cy={y(hover)} r="4" fill="#f2e3c7"/>
                    </g>
                  )}
                </svg>
                {hover&&(
                  <div className="profile-tooltip">
                    <b>{(hover.distance/1000).toFixed(2)} km</b>
                    <span>Elevation {hover.z===null?'unavailable':hover.z.toFixed(0)+' m'}</span>
                    <span>Slope {hover.slope===null?'unavailable':hover.slope.toFixed(1)+'°'}</span>
                    {hover.roughness!==null&&<span>Roughness {hover.roughness.toFixed(2)}</span>}
                    <span>Support: {hover.support_tier}</span>
                  </div>
                )}
              </div>
            </>
          ):(
            <div className={'empty-profile '+(busy?'shimmer':'')}>{busy?'Analyzing terrain…':route?'Elevation profile unavailable — 2D planar route.':'Elevation observations appear after route generation.'}</div>
          )
        )}

        {activeTab==='clock'&&mc&&(
          <div className="mission-clock-panel" style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:'10px',fontSize:'12px',color:'#d5e3df'}}>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)'}}>
              <div style={{color:'#8fa6a0',fontSize:'11px'}}>DEPARTURE (MARS24)</div>
              <strong style={{fontSize:'13.5px',color:'#9becbf'}}>{mc.departure_ltst_hms} LTST</strong>
              <div>UTC: <code>{mc.departure_utc}</code></div>
              <div>Solar Elevation: <b>{mc.departure_solar_elevation_deg}°</b> · Ls: <b>{mc.departure_ls_deg}°</b></div>
            </div>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)'}}>
              <div style={{color:'#8fa6a0',fontSize:'11px'}}>COMPLETION &amp; DAYLIGHT</div>
              <strong style={{fontSize:'13.5px',color:(mc.exceeds_daylight_window ?? mc.darkness_encountered)?'#ffb867':'#9becbf'}}>{mc.completion_ltst_hms} LTST</strong>
              <div>UTC: <code>{mc.completion_utc}</code></div>
              <div>Available Daylight at Start: <b>{mc.available_daylight_at_departure_hours} h</b></div>
            </div>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)'}}>
              <div style={{color:'#8fa6a0',fontSize:'11px'}}>ILLUMINATION &amp; DEM SHADOWS</div>
              <strong style={{fontSize:'13.5px',color:mc.darkness_distance_m>0||mc.terrain_shadowed_distance_m>0?'#ffb867':'#9becbf'}}>
                {mc.darkness_distance_m===0&&mc.terrain_shadowed_distance_m===0?'100% Illuminated':'Shadow/Night Exposure'}
              </strong>
              <div>Night / Darkness: <b>{mc.darkness_distance_m} m ({((mc.darkness_fraction||0)*100).toFixed(1)}%)</b></div>
              <div>DEM Terrain Shadow: <b>{mc.terrain_shadowed_distance_m} m ({((mc.terrain_shadowed_fraction||0)*100).toFixed(1)}%)</b></div>
            </div>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)'}}>
              <div style={{color:'#8fa6a0',fontSize:'11px'}}>OUTBOUND &amp; RETURN LEGS</div>
              <strong style={{fontSize:'13.5px',color:'#e3f2ed'}}>{mc.total_mission_duration_hours ?? mc.total_duration_hours} h Total EVA</strong>
              <div>Outbound: <b>{((mc.outbound_leg?.distance_m||0)/1000).toFixed(2)} km ({mc.outbound_leg?.total_duration_hours ?? mc.outbound_leg?.walking_duration_hours} h)</b></div>
              <div>Cost Function Modified: <b>{mc.cost_function_modified?'Yes':'No (Strict Evaluation Layer)'}</b></div>
            </div>
          </div>
        )}

        {activeTab==='uncertainty'&&unc&&(
          <div className="uncertainty-recon-panel" style={{display:'grid',gridTemplateColumns:'1fr 1.3fr',gap:'12px',fontSize:'12px',color:'#d5e3df'}}>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)'}}>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
                <strong>Terrain Data Support Tiers</strong>
                <span style={{color:'#9becbf',fontWeight:600}}>Overall: {unc.overall_support_tier} (Exposure: {unc.uncertainty_exposure_score}/100)</span>
              </div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'6px',marginTop:'8px'}}>
                {['STRONG','MODERATE','WEAK','UNKNOWN'].map(tier=>{
                  const distM = unc.tier_distances_m?.[tier] ?? unc[`${tier.toLowerCase()}_support_m`] ?? 0;
                  const frac = unc.tier_fractions?.[tier] ?? unc[`${tier.toLowerCase()}_fraction`] ?? 0;
                  return (
                    <div key={tier} style={{padding:'6px',borderRadius:'6px',background:'rgba(0,0,0,0.25)',border:'1px solid rgba(255,255,255,0.06)'}}>
                      <div style={{fontSize:'10px',color:tier==='STRONG'?'#5cffb0':tier==='MODERATE'?'#64dfdf':tier==='WEAK'?'#ffb867':'#ff6b6b'}}>{tier}</div>
                      <div style={{fontWeight:600}}>{Math.round(distM)} m</div>
                      <small style={{color:'#8fa6a0'}}>{(frac*100).toFixed(1)}%</small>
                    </div>
                  );
                })}
              </div>
              <div style={{marginTop:'6px',fontSize:'11px',color:'#8fa6a0'}}>
                Source: {unc.dem_source ?? unc.dem_source_id} ({unc.dem_resolution_m} m grid)
              </div>
            </div>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)',maxHeight:'150px',overflowY:'auto'}}>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
                <strong>Next-Best Reconnaissance Planner</strong>
                <span style={{fontSize:'10.5px',color:'#64dfdf'}}>Policy: Existing NASA Archives First</span>
              </div>
              {(recon?.recommendations||[]).map((rec,idx)=>{
                const rType = rec.recommendation_type ?? rec.recommended_action_type ?? 'EXISTING_NASA_OBSERVATIONS';
                const isExisting = rType.includes('EXISTING') || rType.includes('ARCHIVE');
                const inst = rec.instrument ?? rec.existing_nasa_observations?.[0]?.instrument ?? 'HiRISE / CTX Stereo';
                const redPct = rec.expected_uncertainty_reduction_pct ?? rec.projected_uncertainty_reduction_pct ?? 50;
                const summary = rec.rationale ?? rec.recommendation_summary;
                return (
                  <div key={rec.rank ?? rec.priority_rank ?? idx} style={{marginBottom:'6px',paddingBottom:'6px',borderBottom:'1px solid rgba(255,255,255,0.06)'}}>
                    <span style={{padding:'1px 6px',borderRadius:'4px',fontSize:'10px',marginRight:'6px',background:isExisting?'rgba(92,255,176,0.18)':'rgba(255,184,103,0.18)',color:isExisting?'#9becbf':'#ffb867'}}>
                      {rType}
                    </span>
                    <b>{inst}</b> <small style={{color:'#9becbf'}}>(-{redPct}% uncertainty)</small>
                    <div style={{fontSize:'11px',color:'#b8c7c3',marginTop:'2px'}}>{summary}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {activeTab==='science'&&sci&&(
          <div className="science-pareto-panel" style={{display:'grid',gridTemplateColumns:'1fr 1.2fr',gap:'12px',fontSize:'12px',color:'#d5e3df'}}>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)',maxHeight:'150px',overflowY:'auto'}}>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
                <strong>Science Return per EVA Hour</strong>
                <span style={{color:'#ffd166',fontWeight:700}}>{sci.science_return_per_eva_hour} pts / EVA hr</span>
              </div>
              <div style={{fontSize:'11px',marginBottom:'6px',color:'#a7bab5'}}>
                Targets Visited: <b>{sci.visited_targets_count}</b> · Science Value: <b>{sci.total_science_value_points ?? sci.total_science_score ?? sci.total_science_value} pts</b> · Total EVA: <b>{sci.total_eva_duration_hours} h / {sci.max_eva_budget_hours ?? sci.max_eva_hours ?? 8} h</b> ({sci.within_eva_budget !== false ? 'Within Budget' : 'Over Budget'})
              </div>
              {(sci.visited_targets||[]).map(t=>(
                <div key={t.target_id} style={{fontSize:'11px',padding:'4px 0',borderTop:'1px solid rgba(255,255,255,0.06)'}}>
                  <b style={{color:'#ffe8a3'}}>★ {t.name}</b> ({t.science_value_points ?? t.total_science_value ?? t.science_value} pts, {t.stop_duration_min ?? t.recommended_stop_minutes ?? t.stop_duration_minutes} min stop, {Math.round(t.detour_distance_m ?? t.closest_approach_m ?? 0)} m approach) — <span style={{color:'#9cb0ab'}}>{t.geologic_unit}</span>
                </div>
              ))}
            </div>
            <div style={{background:'rgba(255,255,255,0.03)',padding:'10px',borderRadius:'8px',border:'1px solid rgba(255,255,255,0.07)',maxHeight:'150px',overflowY:'auto'}}>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
                <strong>4-Objective Pareto Frontier ({pareto?.pareto_optimal_count||1}/{pareto?.total_candidates_count ?? pareto?.total_candidates ?? 1} Non-Dominated)</strong>
              </div>
              <table style={{width:'100%',fontSize:'11px',borderCollapse:'collapse'}}>
                <thead>
                  <tr style={{color:'#8fa6a0',textAlign:'left',borderBottom:'1px solid rgba(255,255,255,0.08)'}}>
                    <th>Candidate</th><th>Archetype</th><th>EVA (h)</th><th>Hazard</th><th>Uncert.</th><th>Sci/h</th><th>Pareto</th>
                  </tr>
                </thead>
                <tbody>
                  {(pareto?.candidates||[]).map(c=>(
                    <tr key={c.route_id} style={{borderBottom:'1px solid rgba(255,255,255,0.04)'}}>
                      <td><b>{c.name ?? c.label}</b></td>
                      <td>{c.pareto_archetype}</td>
                      <td>{c.objectives?.duration_hours ?? c.duration_hours}</td>
                      <td>{c.objectives?.hazard_score ?? c.terrain_hazard_score}</td>
                      <td>{c.objectives?.uncertainty_exposure_score ?? c.uncertainty_exposure_score}</td>
                      <td>{c.objectives?.science_return_per_eva_hour ?? c.science_return_per_eva_hour}</td>
                      <td style={{color:c.is_pareto_optimal?'#5cffb0':'#ffb867'}}>{c.is_pareto_optimal?'OPTIMAL':'DOMINATED'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab==='stress'&&stress&&(
          <div className="stress-suite-panel" style={{fontSize:'11.5px',color:'#d5e3df',maxHeight:'155px',overflowY:'auto'}}>
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
              <strong>Deterministic 7-Scenario Operational Mission Stress Suite (Baseline Preserved)</strong>
              <span style={{color:'#9becbf',fontWeight:600}}>
                {stress.scenarios_passed_count} PASS · {stress.scenarios_marginal_count ?? (stress.scenarios||[]).filter(s=>s.status==='MARGINAL').length} MARGINAL · {stress.scenarios_failed_count ?? (stress.scenarios||[]).filter(s=>s.status==='FAIL').length} FAIL ({stress.overall_stress_resilience_pct}% Resilience)
              </span>
            </div>
            <table style={{width:'100%',borderCollapse:'collapse'}}>
              <thead>
                <tr style={{color:'#8fa6a0',textAlign:'left',borderBottom:'1px solid rgba(255,255,255,0.08)'}}>
                  <th>Scenario</th><th>Status</th><th>Stressed Metric</th><th>Baseline / Limit</th><th>Engineering Rationale</th>
                </tr>
              </thead>
              <tbody>
                {(stress.scenarios||[]).map(sc=>(
                  <tr key={sc.scenario_id} style={{borderBottom:'1px solid rgba(255,255,255,0.05)'}}>
                    <td style={{padding:'3px 4px'}}><b>{sc.name ?? sc.title}</b></td>
                    <td style={{padding:'3px 4px',fontWeight:700,color:sc.status==='PASS'?'#5cffb0':sc.status==='MARGINAL'?'#ffb867':'#ff6b6b'}}>{sc.status}</td>
                    <td style={{padding:'3px 4px'}}>{sc.effective_duration_hours !== undefined ? `${sc.effective_duration_hours} h` : sc.stressed_metric}</td>
                    <td style={{padding:'3px 4px'}}>{sc.max_slope_deg !== undefined ? `${sc.max_slope_deg}° / ${sc.slope_limit_deg}°` : sc.baseline_metric}</td>
                    <td style={{padding:'3px 4px',color:'#a9bcb7'}}>{sc.rationale ?? sc.explanation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
