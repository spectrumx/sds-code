/** Colormap RGB for normalized power [0,1]. */
export function colorForNormalizedPower(colorMap, normalizedPower) {
    const intensity = Math.floor(normalizedPower * 255)
    switch (colorMap) {
        case "viridis": {
            // Blue to green to yellow to red
            if (normalizedPower < 0.25) {
                return `rgb(0, ${Math.floor(intensity * 4)}, ${255 - intensity})`
            }
            if (normalizedPower < 0.5) {
                const t = (normalizedPower - 0.25) * 4
                return `rgb(0, 255, ${Math.floor(255 * (1 - t))})`
            }
            if (normalizedPower < 0.75) {
                const t = (normalizedPower - 0.5) * 4
                return `rgb(${Math.floor(255 * t)}, 255, 0)`
            }
            const t = (normalizedPower - 0.75) * 4
            return `rgb(255, ${Math.floor(255 * (1 - t))}, 0)`
        }
        case "plasma": {
            // Purple to blue to green to yellow to red
            if (normalizedPower < 0.25) {
                return `rgb(${Math.floor(intensity * 4)}, 0, ${255 - intensity})`
            }
            if (normalizedPower < 0.5) {
                const t = (normalizedPower - 0.25) * 4
                return `rgb(255, 0, ${Math.floor(255 * (1 - t))})`
            }
            if (normalizedPower < 0.75) {
                const t = (normalizedPower - 0.5) * 4
                return `rgb(255, ${Math.floor(255 * t)}, 0)`
            }
            const t = (normalizedPower - 0.75) * 4
            return `rgb(255, 255, ${Math.floor(255 * t)})`
        }
        case "hot": {
            // Black to red to yellow to white
            if (normalizedPower < 0.33) {
                const t = normalizedPower * 3
                return `rgb(${Math.floor(255 * t)}, 0, 0)`
            }
            if (normalizedPower < 0.67) {
                const t = (normalizedPower - 0.33) * 3
                return `rgb(255, ${Math.floor(255 * t)}, 0)`
            }
            const t = (normalizedPower - 0.67) * 3
            return `rgb(255, 255, ${Math.floor(255 * t)})`
        }
        case "gray":
            return `rgb(${intensity}, ${intensity}, ${intensity})`
        case "inferno": {
            // Black to purple to red to yellow
            if (normalizedPower < 0.33) {
                const t = normalizedPower * 3
                return `rgb(${Math.floor(128 * t)}, 0, ${Math.floor(255 * t)})`
            }
            if (normalizedPower < 0.67) {
                const t = (normalizedPower - 0.33) * 3
                return `rgb(${Math.floor(128 + 127 * t)}, 0, ${Math.floor(255 - 255 * t)})`
            }
            const t = (normalizedPower - 0.67) * 3
            return `rgb(255, ${Math.floor(255 * t)}, 0)`
        }
        case "magma": {
            // Black to purple to pink to white
            if (normalizedPower < 0.33) {
                const t = normalizedPower * 3
                return `rgb(${Math.floor(128 * t)}, 0, ${Math.floor(255 * t)})`
            }
            if (normalizedPower < 0.67) {
                const t = (normalizedPower - 0.33) * 3
                return `rgb(${Math.floor(128 + 127 * t)}, 0, ${Math.floor(255 - 127 * t)})`
            }
            const t = (normalizedPower - 0.67) * 3
            return `rgb(255, ${Math.floor(255 * t)}, ${Math.floor(128 + 127 * t)})`
        }
        default: {
            // Default to viridis-like blue to green to yellow to red
            if (normalizedPower < 0.25) {
                return `rgb(0, ${Math.floor(intensity * 4)}, ${255 - intensity})`
            }
            if (normalizedPower < 0.5) {
                const t = (normalizedPower - 0.25) * 4
                return `rgb(0, 255, ${Math.floor(255 * (1 - t))})`
            }
            if (normalizedPower < 0.75) {
                const t = (normalizedPower - 0.5) * 4
                return `rgb(${Math.floor(255 * t)}, 255, 0)`
            }
            const t = (normalizedPower - 0.75) * 4
            return `rgb(255, ${Math.floor(255 * (1 - t))}, 0)`
        }
    }
}
