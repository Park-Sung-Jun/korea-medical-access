// Vercel 서버리스 함수 — OpenRouteService 등시선 프록시.
// ORS 키를 서버측 환경변수(ORS_KEY)에 보관해 브라우저로 노출하지 않는다.
// 호출: /api/iso?lng=127.0&lat=37.5  → ORS isochrone GeoJSON 반환.
module.exports = async (req, res) => {
  const lng = parseFloat(req.query.lng);
  const lat = parseFloat(req.query.lat);
  if (!isFinite(lng) || !isFinite(lat)) {
    return res.status(400).json({ error: 'lng, lat 쿼리가 필요합니다.' });
  }
  const key = process.env.ORS_KEY;
  if (!key) {
    return res.status(500).json({ error: 'ORS_KEY 환경변수가 설정되지 않았습니다.' });
  }
  try {
    const r = await fetch('https://api.openrouteservice.org/v2/isochrones/driving-car', {
      method: 'POST',
      headers: { Authorization: key, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        locations: [[lng, lat]],
        range: [900, 1800, 2700, 3600],
        range_type: 'time',
      }),
    });
    const text = await r.text();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 's-maxage=86400, stale-while-revalidate=604800');
    return res.status(r.status).send(text);
  } catch (e) {
    return res.status(502).json({ error: 'ORS 호출 실패: ' + String(e) });
  }
};
