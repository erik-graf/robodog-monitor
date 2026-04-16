// logic for real-time updates and visualization
const canvas = document.getElementById('pathCanvas');
const ctx = canvas.getContext('2d');
const currentCoordsDisplay = document.getElementById('current-coords');

const canvasWidth = canvas.offsetWidth;
const canvasHeight = canvas.offsetHeight;
canvas.width = canvasWidth;
canvas.height = canvasHeight;
const padding = 50;

// Fixed coordinate bounds — covers rectangle, deviation point, and all cameras with margin
const BOUNDS = {
    minLat: 48.2045,
    maxLat: 48.2125,
    minLon: 16.3705,
    maxLon: 16.3800
};

// Regular patrol rectangle corners (SW → NW → NE → SE)
const RECT = [
    { lat: 48.2075, lon: 16.3728 },
    { lat: 48.2112, lon: 16.3728 },
    { lat: 48.2112, lon: 16.3778 },
    { lat: 48.2075, lon: 16.3778 },
];

// 7 surveillance cameras — camera 7 is the deviation point
const CAMERAS = [
    { lat: 48.2075, lon: 16.3728, id: 1 },
    { lat: 48.2112, lon: 16.3728, id: 2 },
    { lat: 48.2112, lon: 16.3778, id: 3 },
    { lat: 48.2075, lon: 16.3778, id: 4 },
    { lat: 48.2094, lon: 16.3715, id: 5 },
    { lat: 48.2094, lon: 16.3792, id: 6 },
    { lat: 48.2060, lon: 16.3753, id: 7 },
];

function toCanvas(lat, lon) {
    const x = padding + (lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon) * (canvasWidth - 2 * padding);
    const y = canvasHeight - padding - (lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat) * (canvasHeight - 2 * padding);
    return { x, y };
}

const history = [];
const MAX_DOTS = 10;

async function updateCoordinates() {
    try {
        const response = await fetch('/data');
        const data = await response.json();

        if (data.length > 0) {
            const latest = data[data.length - 1];
            currentCoordsDisplay.textContent =
                `Lat: ${latest.latitude}, Lon: ${latest.longitude}`;

            const lastPoints = data.slice(-MAX_DOTS);

            history.length = 0;
            history.push(...lastPoints);

            drawPath();
        }
    } catch (error) {
        console.error("Failed to fetch coordinates:", error);
    }
}

// async function updateCoordinates() {
//     try {
//         const response = await fetch('/data');
//         const data = await response.json();
// 
//         if (data.length > 0) {
//             const latest = data[data.length - 1];
//             currentCoordsDisplay.textContent = `Lat: ${latest.latitude}, Lon: ${latest.longitude}`;
//             history.length = 0;
//             history.push(...data);
//             drawPath();
//         }
//     } catch (error) {
//         console.error("Failed to fetch coordinates:", error);
//     }
// }
// 
function drawPath() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw grid
    ctx.strokeStyle = 'rgba(78, 115, 142, 0.3)';
    ctx.lineWidth = 1;
    const gridStep = 0.001;
    const startLat = Math.ceil(BOUNDS.minLat / gridStep) * gridStep;
    const startLon = Math.ceil(BOUNDS.minLon / gridStep) * gridStep;
    for (let lat = startLat; lat <= BOUNDS.maxLat; lat += gridStep) {
        const { y } = toCanvas(lat, BOUNDS.minLon);
        const { x: x1 } = toCanvas(lat, BOUNDS.maxLon);
        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(x1, y);
        ctx.stroke();
    }
    for (let lon = startLon; lon <= BOUNDS.maxLon; lon += gridStep) {
        const { x } = toCanvas(BOUNDS.minLat, lon);
        const { y: y0 } = toCanvas(BOUNDS.maxLat, lon);
        const { y: y1 } = toCanvas(BOUNDS.minLat, lon);
        ctx.beginPath();
        ctx.moveTo(x, y0);
        ctx.lineTo(x, y1);
        ctx.stroke();
    }

    // Draw regular patrol route underlay
    ctx.strokeStyle = 'rgba(0, 200, 100, 0.25)';
    ctx.lineWidth = 24;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    RECT.forEach((pt, i) => {
        const { x, y } = toCanvas(pt.lat, pt.lon);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();

history.forEach((point, index) => {
    const { x, y } = toCanvas(point.latitude, point.longitude);
    const isNewest = index === history.length - 1;
    const opacity = 0.1 + 0.9 * (index / Math.max(history.length - 1, 1));

    ctx.fillStyle = `rgba(37, 143, 255, ${opacity})`;
    ctx.beginPath();
    ctx.arc(x, y, isNewest ? 6 : 5, 0, Math.PI * 2);
    ctx.fill();
});

  //  // Draw actual GPS path (dots, fading older points)
  //  history.forEach((point, index) => {
  //      const { x, y } = toCanvas(point.latitude, point.longitude);
  //      const opacity = (index) / (history.length);
  //      ctx.fillStyle = `rgba(37, 143, 255, ${opacity})`;
  //      ctx.beginPath();
  //      ctx.arc(x, y, 5, 0, Math.PI * 2);
  //      ctx.fill();
  //      ctx.closePath();
  //  });

    // Draw cameras as numbered circles (on top of path dots)
    CAMERAS.forEach(cam => {
        const { x, y } = toCanvas(cam.lat, cam.lon);
        ctx.fillStyle = 'rgba(180, 50, 50, 0.85)';
        ctx.beginPath();
        ctx.arc(x, y, 12, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'white';
        ctx.font = 'bold 11px Courier New';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(cam.id, x, y);
    });
}

// Start fetch data every 2 seconds to match publish interval
setInterval(updateCoordinates, 1000);
setTimeout(updateCoordinates, 500);
updateCoordinates();
