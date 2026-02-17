
// ADC Academy - Nigeria Restoration Texture-Based Interface (Three.js)
let scene, camera, renderer, nigeriaMap, handshakeSprite, stars;
let mouseX = 0, mouseY = 0;
let windowHalfX = window.innerWidth / 2;
let windowHalfY = window.innerHeight / 2;

// Animation state
let isRestored = false;
let handshakeAlpha = 0;
let transitionProgress = 0;

// High-fidelity SVG Silhouettes for Textures
const NIGERIA_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 450">
    <path fill="white" d="M100,50 L150,40 L180,45 L220,30 L260,40 L300,35 L340,50 L380,45 L420,60 L450,90 L460,130 L440,170 L460,210 L440,250 L420,280 L440,320 L420,360 L400,380 L360,400 L320,410 L280,420 L240,410 L200,420 L160,410 L120,420 L80,410 L40,380 L30,340 L50,300 L30,260 L50,220 L30,180 L50,140 L40,100 L70,70 Z"/>
</svg>`;

const HANDSHAKE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
    <path fill="white" d="M10,50 Q40,20 70,50 Q100,80 130,50 Q160,20 190,50 L190,60 Q160,30 130,60 Q100,90 70,60 Q40,30 10,60 Z"/>
    <path fill="white" d="M70,45 Q75,35 85,35 Q95,35 100,45 M100,45 Q105,35 115,35 Q125,35 130,45"/>
</svg>`;

function init() {
    const container = document.getElementById('canvas-container');
    if (!container) return;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 5000);
    camera.position.set(0, 50, 800);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    createEnvironment();

    // Create Map and Sprite using Canvas Textures
    const nigeriaTex = createSVGTexture(NIGERIA_SVG, 512, 512);
    const handshakeTex = createSVGTexture(HANDSHAKE_SVG, 512, 256);

    createNigeriaMap(nigeriaTex);
    createHandshakeSprite(handshakeTex);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const mainLight = new THREE.PointLight(0xffffff, 2, 3000);
    mainLight.position.set(200, 500, 300);
    scene.add(mainLight);

    document.addEventListener('mousemove', onDocumentMouseMove);
    window.addEventListener('resize', onWindowResize);

    animate();
}

function createSVGTexture(svgString, width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');

    const img = new Image();
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    img.onload = function () {
        ctx.drawImage(img, 0, 0, width, height);
        URL.revokeObjectURL(url);
    };
    img.src = url;

    return new THREE.CanvasTexture(canvas);
}

function createEnvironment() {
    const starCount = 3000;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(starCount * 3);
    const colors = new Float32Array(starCount * 3);

    for (let i = 0; i < starCount; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 5000;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 5000;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 5000;

        const isGreen = Math.random() > 0.7;
        colors[i * 3] = isGreen ? 0.2 : 1;
        colors[i * 3 + 1] = 1;
        colors[i * 3 + 2] = isGreen ? 0.4 : 1;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({ size: 2, vertexColors: true, transparent: true, opacity: 0.6 });
    stars = new THREE.Points(geometry, material);
    scene.add(stars);
}

function createNigeriaMap(texture) {
    // We use a plane with the Nigeria Map texture and a custom shader for colors
    const geometry = new THREE.PlaneGeometry(600, 550, 100, 100);

    // Custom shader to handle Red North / Black South and transition to Green
    const material = new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uTexture: { value: texture },
            uTransition: { value: 0 },
            uRestored: { value: 0 }
        },
        vertexShader: `
            varying vec2 vUv;
            uniform float uTime;
            void main() {
                vUv = uv;
                vec3 pos = position;
                pos.z += sin(pos.x * 0.01 + uTime) * 10.0;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
            }
        `,
        fragmentShader: `
            varying vec2 vUv;
            uniform sampler2D uTexture;
            uniform float uTransition;
            uniform float uRestored;
            void main() {
                vec4 tex = texture2D(uTexture, vUv);
                if (tex.a < 0.1) discard;

                vec3 northColor = vec3(0.9, 0.1, 0.1); // Red
                vec3 southColor = vec3(0.05, 0.05, 0.05); // Black
                vec3 finalGreen = vec3(0.13, 0.77, 0.36); // Emerald Green

                vec3 baseColor = mix(southColor, northColor, step(0.5, vUv.y));
                vec3 color = mix(baseColor, finalGreen, uTransition);

                gl_FragColor = vec4(color, tex.r * 0.9);
            }
        `,
        transparent: true,
        side: THREE.DoubleSide
    });

    nigeriaMap = new THREE.Mesh(geometry, material);
    nigeriaMap.position.y = 50;
    scene.add(nigeriaMap);
}

function createHandshakeSprite(texture) {
    const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        opacity: 0,
        color: 0xffffff
    });
    handshakeSprite = new THREE.Sprite(material);
    handshakeSprite.scale.set(400, 200, 1);
    handshakeSprite.position.set(0, -200, 50);
    scene.add(handshakeSprite);
}

function animate() {
    requestAnimationFrame(animate);
    const time = Date.now() * 0.001;

    // Logic: Transition to Green after 3 seconds
    if (time > 3 && !isRestored) {
        transitionProgress += 0.01;
        if (transitionProgress >= 1) {
            transitionProgress = 1;
            isRestored = true;
        }
    }

    // Apply uniforms
    if (nigeriaMap) {
        nigeriaMap.material.uniforms.uTime.value = time;
        nigeriaMap.material.uniforms.uTransition.value = transitionProgress;
    }

    // Handshake sprite appearance (glow up)
    if (isRestored) {
        handshakeAlpha += 0.02;
        if (handshakeAlpha > 0.9) handshakeAlpha = 0.9;
        handshakeSprite.material.opacity = handshakeAlpha;
        handshakeSprite.scale.set(
            400 + Math.sin(time * 2) * 10,
            200 + Math.sin(time * 2) * 5,
            1
        );
    }

    stars.rotation.y += 0.0005;

    camera.position.x += (mouseX * 0.1 - camera.position.x) * 0.05;
    camera.position.y += (-mouseY * 0.1 + 50 - camera.position.y) * 0.05;
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);
}

function onWindowResize() {
    windowHalfX = window.innerWidth / 2;
    windowHalfY = window.innerHeight / 2;
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function onDocumentMouseMove(event) {
    mouseX = (event.clientX - windowHalfX);
    mouseY = (event.clientY - windowHalfY);
}

init();
