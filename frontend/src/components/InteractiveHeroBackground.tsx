"use client";

import { useEffect, useRef } from "react";

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  phase: number;
  opacity: number;
};

type InteractiveHeroBackgroundProps = {
  className?: string;
};

const randomBetween = (min: number, max: number) => Math.random() * (max - min) + min;

export function InteractiveHeroBackground({
  className = "",
}: InteractiveHeroBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    const particles: Particle[] = [];
    const pointer = { x: 0, y: 0, active: false };
    let width = 0;
    let height = 0;
    let lastFrame = 0;
    let animationFrame = 0;
    let isDarkTheme = false;
    let isReducedMotion = false;
    let isVisible = true;

    const getParticleCount = () => {
      const density = isReducedMotion ? 52000 : 32000;
      return Math.max(16, Math.min(42, Math.round((width * height) / density)));
    };

    const syncTheme = () => {
      const root = document.documentElement;
      isDarkTheme = root.classList.contains("dark") || root.dataset.theme === "dark";
    };

    const resetParticles = () => {
      particles.length = 0;
      const count = getParticleCount();
      for (let index = 0; index < count; index += 1) {
        particles.push({
          x: randomBetween(0, width),
          y: randomBetween(0, height),
          vx: randomBetween(-0.18, 0.18),
          vy: randomBetween(-0.12, 0.12),
          radius: randomBetween(1.2, 2.8),
          phase: randomBetween(0, Math.PI * 2),
          opacity: randomBetween(0.32, 0.85),
        });
      }
    };

    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;

      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);

      resetParticles();
    };

    const updatePointer = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const nextX = event.clientX - rect.left;
      const nextY = event.clientY - rect.top;
      const insideBounds = nextX >= 0 && nextX <= rect.width && nextY >= 0 && nextY <= rect.height;

      pointer.active = insideBounds;
      if (!insideBounds) return;

      pointer.x = nextX;
      pointer.y = nextY;
    };

    const clearPointer = () => {
      pointer.active = false;
    };

    const palette = {
      glow: (alpha: number) =>
        isDarkTheme ? `rgba(255, 255, 255, ${alpha})` : `rgba(15, 77, 188, ${alpha})`,
      particle: (alpha: number) =>
        isDarkTheme ? `rgba(255, 255, 255, ${alpha})` : `rgba(21, 79, 188, ${alpha})`,
      particleAccent: (alpha: number) =>
        isDarkTheme ? `rgba(96, 165, 250, ${alpha})` : `rgba(14, 165, 233, ${alpha})`,
      line: (alpha: number) =>
        isDarkTheme ? `rgba(148, 163, 184, ${alpha})` : `rgba(15, 77, 188, ${alpha})`,
    };

    const drawFrame = (timestamp: number) => {
      animationFrame = window.requestAnimationFrame(drawFrame);

      if (!isVisible || document.hidden || width === 0 || height === 0) {
        return;
      }

      const minimumFrameGap = isReducedMotion ? 48 : 32;
      if (lastFrame && timestamp - lastFrame < minimumFrameGap) {
        return;
      }

      const delta = lastFrame ? Math.min(2, (timestamp - lastFrame) / 16.67) : 1;
      lastFrame = timestamp;

      context.clearRect(0, 0, width, height);

      if (pointer.active) {
        const glowRadius = isReducedMotion ? 140 : 220;
        const gradient = context.createRadialGradient(
          pointer.x,
          pointer.y,
          0,
          pointer.x,
          pointer.y,
          glowRadius,
        );
        gradient.addColorStop(0, palette.glow(isDarkTheme ? 0.12 : 0.1));
        gradient.addColorStop(0.5, palette.glow(isDarkTheme ? 0.05 : 0.04));
        gradient.addColorStop(1, palette.glow(0));
        context.fillStyle = gradient;
        context.fillRect(pointer.x - glowRadius, pointer.y - glowRadius, glowRadius * 2, glowRadius * 2);
      }

      for (const particle of particles) {
        const driftStrength = isReducedMotion ? 0.004 : 0.008;
        particle.vx += Math.sin(timestamp * 0.00018 + particle.phase) * driftStrength;
        particle.vy += Math.cos(timestamp * 0.00014 + particle.phase) * driftStrength;

        if (pointer.active) {
          const dx = particle.x - pointer.x;
          const dy = particle.y - pointer.y;
          const distance = Math.hypot(dx, dy) || 1;
          const influenceRadius = isReducedMotion ? 120 : 180;

          if (distance < influenceRadius) {
            const force = (1 - distance / influenceRadius) * (isReducedMotion ? 0.08 : 0.14);
            particle.vx += (dx / distance) * force * delta;
            particle.vy += (dy / distance) * force * delta;
          }
        }

        particle.x += particle.vx * delta;
        particle.y += particle.vy * delta;
        particle.vx *= 0.985;
        particle.vy *= 0.985;

        if (particle.x < -24) particle.x = width + 24;
        if (particle.x > width + 24) particle.x = -24;
        if (particle.y < -24) particle.y = height + 24;
        if (particle.y > height + 24) particle.y = -24;

        context.beginPath();
        context.fillStyle =
          particle.radius > 2.1
            ? palette.particleAccent(particle.opacity * 0.7)
            : palette.particle(particle.opacity);
        context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        context.fill();
      }

      const connectionDistance = isReducedMotion ? 110 : 150;
      for (let sourceIndex = 0; sourceIndex < particles.length; sourceIndex += 1) {
        const source = particles[sourceIndex];
        for (let targetIndex = sourceIndex + 1; targetIndex < particles.length; targetIndex += 1) {
          const target = particles[targetIndex];
          const dx = source.x - target.x;
          const dy = source.y - target.y;
          const distance = Math.hypot(dx, dy);

          if (distance > connectionDistance) continue;

          const alpha = Math.pow(1 - distance / connectionDistance, 1.7) * (isDarkTheme ? 0.2 : 0.14);
          context.beginPath();
          context.moveTo(source.x, source.y);
          context.lineTo(target.x, target.y);
          context.strokeStyle = palette.line(alpha);
          context.lineWidth = 1;
          context.stroke();
        }
      }
    };

    const themeObserver = new MutationObserver(syncTheme);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });

    const reduceMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateReducedMotion = () => {
      isReducedMotion = reduceMotionQuery.matches;
      resetParticles();
    };

    const visibilityObserver = new IntersectionObserver(
      (entries) => {
        isVisible = entries[0]?.isIntersecting ?? true;
      },
      { threshold: 0.05 },
    );

    syncTheme();
    updateReducedMotion();
    resizeCanvas();

    visibilityObserver.observe(canvas);
    window.addEventListener("resize", resizeCanvas);
    window.addEventListener("pointermove", updatePointer, { passive: true });
    window.addEventListener("blur", clearPointer);
    reduceMotionQuery.addEventListener("change", updateReducedMotion);

    animationFrame = window.requestAnimationFrame(drawFrame);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      visibilityObserver.disconnect();
      themeObserver.disconnect();
      window.removeEventListener("resize", resizeCanvas);
      window.removeEventListener("pointermove", updatePointer);
      window.removeEventListener("blur", clearPointer);
      reduceMotionQuery.removeEventListener("change", updateReducedMotion);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
