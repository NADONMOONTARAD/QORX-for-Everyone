import { useEffect, useRef } from "react";
import lottie, { AnimationItem } from "lottie-web";

type LottieIconProps = {
  animationData: object;
  loop?: boolean;
  className?: string;
  play?: boolean;
  speed?: number;
};

export function LottieIcon({
  animationData,
  loop = true,
  className,
  play = true,
  speed = 1,
}: LottieIconProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const animationRef = useRef<AnimationItem | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    animationRef.current = lottie.loadAnimation({
      container: containerRef.current,
      renderer: "svg",
      loop,
      autoplay: play,
      animationData,
    });
    animationRef.current.setSpeed(speed);
    return () => {
      animationRef.current?.destroy();
      animationRef.current = null;
    };
  }, [animationData, loop, play, speed]);

  useEffect(() => {
    const animation = animationRef.current;
    if (!animation) return;
    if (play) {
      animation.setDirection(1);
      animation.setSpeed(speed);
      animation.goToAndPlay(0, true);
    } else {
      animation.goToAndStop(0, true);
    }
  }, [play, speed]);

  return <div ref={containerRef} className={className} />;
}
