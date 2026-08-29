/**
 * Feature: 3x3 Matrix calculation and coordinate transform utilities (Row-major)
 * Purpose: Maintains sub-pixel geometric accuracy across Source Pixel, Canvas World, and Viewport coordinates
 * Path: tool/image_alignment/frontend/matrix_utils.js
 */

const MatrixUtils = (function () {
    'use strict';

    // Create identity 3x3 matrix: [1, 0, 0, 0, 1, 0, 0, 0, 1]
    function identity() {
        return [
            1.0, 0.0, 0.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0
        ];
    }

    // Translation matrix
    function translate(tx, ty) {
        return [
            1.0, 0.0, Number(tx),
            0.0, 1.0, Number(ty),
            0.0, 0.0, 1.0
        ];
    }

    // Ma trận tỉ lệ (Scale)
    function scale(sx, sy) {
        return [
            Number(sx), 0.0, 0.0,
            0.0, Number(sy), 0.0,
            0.0, 0.0, 1.0
        ];
    }

    // Ma trận xoay (Rotate góc radian)
    function rotate(rad) {
        const c = Math.cos(rad);
        const s = Math.sin(rad);
        return [
            c, -s, 0.0,
            s,  c, 0.0,
            0.0, 0.0, 1.0
        ];
    }

    // Nhân 2 ma trận 3x3: C = A * B
    function multiply(a, b) {
        const out = new Array(9);
        for (let r = 0; r < 3; r++) {
            for (let c = 0; c < 3; c++) {
                out[r * 3 + c] = 
                    a[r * 3 + 0] * b[0 * 3 + c] +
                    a[r * 3 + 1] * b[1 * 3 + c] +
                    a[r * 3 + 2] * b[2 * 3 + c];
            }
        }
        return out;
    }

    // Nghịch đảo ma trận 3x3
    function inverse(m) {
        const a00 = m[0], a01 = m[1], a02 = m[2];
        const a10 = m[3], a11 = m[4], a12 = m[5];
        const a20 = m[6], a21 = m[7], a22 = m[8];

        const b01 = a22 * a11 - a12 * a21;
        const b11 = -a22 * a10 + a12 * a20;
        const b21 = a21 * a10 - a11 * a20;

        const det = a00 * b01 + a01 * b11 + a02 * b21;
        if (Math.abs(det) < 1e-12 || !isFinite(det)) {
            return null;
        }

        const invDet = 1.0 / det;
        return [
            b01 * invDet,
            (-a22 * a01 + a02 * a21) * invDet,
            (a12 * a01 - a02 * a11) * invDet,
            b11 * invDet,
            (a22 * a00 - a02 * a20) * invDet,
            (-a12 * a00 + a02 * a10) * invDet,
            b21 * invDet,
            (-a21 * a00 + a01 * a20) * invDet,
            (a11 * a00 - a01 * a10) * invDet
        ];
    }

    // Ánh xạ điểm (x, y) qua ma trận m
    function transformPoint(m, x, y) {
        const px = m[0] * x + m[1] * y + m[2];
        const py = m[3] * x + m[4] * y + m[5];
        const w  = m[6] * x + m[7] * y + m[8];
        if (Math.abs(w - 1.0) > 1e-9 && Math.abs(w) > 1e-12) {
            return [px / w, py / w];
        }
        return [px, py];
    }

    // Trích xuất các tham số trực quan (tx, ty, scale, angle_deg) từ ma trận Affine
    function decompose(m) {
        const tx = m[2];
        const ty = m[5];
        const a = m[0];
        const b = m[3];
        const scaleX = Math.sqrt(a * a + b * b);
        const angleRad = Math.atan2(b, a);
        const angleDeg = (angleRad * 180.0) / Math.PI;
        return { tx, ty, scale: scaleX, angleDeg, angleRad };
    }

    // Tạo ma trận từ translation, scale, rotation quanh tâm (cx, cy)
    function composeFromOrigin(tx, ty, scaleFactor, angleRad, cx = 0, cy = 0) {
        // T(tx, ty) * T(cx, cy) * R(angle) * S(scale) * T(-cx, -cy)
        const t1 = translate(-cx, -cy);
        const s = scale(scaleFactor, scaleFactor);
        const r = rotate(angleRad);
        const t2 = translate(cx + tx, cy + ty);
        return multiply(t2, multiply(r, multiply(s, t1)));
    }

    return {
        identity,
        translate,
        scale,
        rotate,
        multiply,
        inverse,
        transformPoint,
        decompose,
        composeFromOrigin
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = MatrixUtils;
}
