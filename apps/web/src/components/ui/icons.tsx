import React from 'react';

type IconProps = { className?: string };

function BaseIcon({ className, children }: React.PropsWithChildren<IconProps>) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className={className} aria-hidden='true'>
      {children}
    </svg>
  );
}

export const Mountain = (p: IconProps) => <BaseIcon {...p}><path d='m3 20 6-9 4 6 3-4 5 7' /></BaseIcon>;
export const PlusCircle = (p: IconProps) => <BaseIcon {...p}><circle cx='12' cy='12' r='9' /><path d='M12 8v8M8 12h8' /></BaseIcon>;
export const Activity = (p: IconProps) => <BaseIcon {...p}><path d='M3 12h4l3-7 4 14 3-7h4' /></BaseIcon>;
export const Gauge = (p: IconProps) => <BaseIcon {...p}><path d='M4 14a8 8 0 1 1 16 0' /><path d='m12 14 4-4' /></BaseIcon>;
export const Link2 = (p: IconProps) => <BaseIcon {...p}><path d='M10 13a5 5 0 0 1 0-7l1-1a5 5 0 1 1 7 7l-1 1' /><path d='M14 11a5 5 0 0 1 0 7l-1 1a5 5 0 0 1-7-7l1-1' /></BaseIcon>;
export const LogOut = (p: IconProps) => <BaseIcon {...p}><path d='M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4' /><path d='m16 17 5-5-5-5' /><path d='M21 12H9' /></BaseIcon>;
export const Moon = (p: IconProps) => <BaseIcon {...p}><path d='M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z' /></BaseIcon>;
export const Sun = (p: IconProps) => <BaseIcon {...p}><circle cx='12' cy='12' r='4' /><path d='M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4' /></BaseIcon>;
export const UserCircle2 = (p: IconProps) => <BaseIcon {...p}><circle cx='12' cy='8' r='3' /><path d='M5 20a7 7 0 0 1 14 0' /><circle cx='12' cy='12' r='10' /></BaseIcon>;
export const AlertTriangle = (p: IconProps) => <BaseIcon {...p}><path d='m12 3 10 18H2L12 3z' /><path d='M12 9v5M12 17h.01' /></BaseIcon>;
export const Flame = (p: IconProps) => <BaseIcon {...p}><path d='M12 2s4 3 4 7a4 4 0 1 1-8 0c0-3 4-7 4-7z' /><path d='M10 14a2 2 0 1 0 4 0c0-1-2-3-2-3s-2 2-2 3z' /></BaseIcon>;
export const HeartPulse = (p: IconProps) => <BaseIcon {...p}><path d='M20.8 6.5A5.5 5.5 0 0 0 12 6.1a5.5 5.5 0 0 0-8.8 6.8L12 22l8.8-9.1a5.5 5.5 0 0 0 0-6.4z' /><path d='M3 12h4l2-3 2 6 2-3h4' /></BaseIcon>;
export const Lightbulb = (p: IconProps) => <BaseIcon {...p}><path d='M9 18h6M10 22h4M12 2a7 7 0 0 0-4 13v2h8v-2a7 7 0 0 0-4-13z' /></BaseIcon>;
export const Route = (p: IconProps) => <BaseIcon {...p}><circle cx='6' cy='19' r='2' /><circle cx='18' cy='5' r='2' /><path d='M8 18c5-2 6-6 8-11' /></BaseIcon>;
export const Search = (p: IconProps) => <BaseIcon {...p}><circle cx='11' cy='11' r='7' /><path d='m20 20-3.5-3.5' /></BaseIcon>;
export const RefreshCcw = (p: IconProps) => <BaseIcon {...p}><path d='M3 12a9 9 0 0 1 15.5-6.4L21 8' /><path d='M21 3v5h-5' /><path d='M21 12a9 9 0 0 1-15.5 6.4L3 16' /><path d='M3 21v-5h5' /></BaseIcon>;
export const Unplug = (p: IconProps) => <BaseIcon {...p}><path d='M19 7 7 19' /><path d='M8 6 6 8a4 4 0 0 0 6 6l2-2' /><path d='M14 10a4 4 0 0 0 4-4V4' /></BaseIcon>;
export const PersonStanding = (p: IconProps) => <BaseIcon {...p}><circle cx='12' cy='4' r='2' /><path d='M11 7h2l2 5-2 2v6h-2v-5h-2v5H7v-6l2-2 2-5z' /></BaseIcon>;
export const Bike = (p: IconProps) => <BaseIcon {...p}><circle cx='6' cy='17' r='4' /><circle cx='18' cy='17' r='4' /><path d='M10 17 13 9h3l2 8M10 17 8 12h4' /></BaseIcon>;
export const Waves = (p: IconProps) => <BaseIcon {...p}><path d='M2 16c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2' /><path d='M2 11c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2' /></BaseIcon>;
export const Target = (p: IconProps) => <BaseIcon {...p}><circle cx='12' cy='12' r='8' /><circle cx='12' cy='12' r='4' /><circle cx='12' cy='12' r='1' /></BaseIcon>;
export const Calendar = (p: IconProps) => <BaseIcon {...p}><rect x='3' y='5' width='18' height='16' rx='2' /><path d='M16 3v4M8 3v4M3 10h18' /></BaseIcon>;
export const Ruler = (p: IconProps) => <BaseIcon {...p}><rect x='3' y='7' width='18' height='10' rx='2' /><path d='M7 7v3M11 7v2M15 7v3M19 7v2' /></BaseIcon>;
export const Weight = (p: IconProps) => <BaseIcon {...p}><path d='M7 9a5 5 0 1 1 10 0' /><path d='M5 9h14l1 10H4L5 9z' /><path d='M12 12v3' /></BaseIcon>;
export const Shoe = (p: IconProps) => <BaseIcon {...p}><path d='M3 16c2.5 0 3.5-2.5 5-4l2 1.5c1.2.9 2.7 1.5 4.2 1.5H21v3H3z' /><path d='M13 11V7h2v5' /></BaseIcon>;
export const Sparkles = (p: IconProps) => <BaseIcon {...p}><path d='m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2z' /><path d='m5 14 .7 2.3L8 17l-2.3.7L5 20l-.7-2.3L2 17l2.3-.7z' /><path d='m19 14 .7 2.3L22 17l-2.3.7L19 20l-.7-2.3L16 17l2.3-.7z' /></BaseIcon>;
export const MessageSquare = (p: IconProps) => <BaseIcon {...p}><path d='M4 5h16v10H8l-4 4z' /></BaseIcon>;
export const Settings2 = (p: IconProps) => <BaseIcon {...p}><path d='M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z' /><path d='M3 12h2M19 12h2M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4' /></BaseIcon>;
