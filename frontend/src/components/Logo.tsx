export function LogoFull({className}: {className?: string}) {
  return (
    <svg
      className={className}
      width="32"
      height="32"
      viewBox="0 0 240 240"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient
          id="logo-bg"
          x1="0"
          y1="0"
          x2="240"
          y2="240"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#E3032E" />
          <stop offset="1" stopColor="#B8022A" />
        </linearGradient>
        <linearGradient
          id="logo-accent"
          x1="60"
          y1="60"
          x2="180"
          y2="180"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#fecdd3" />
        </linearGradient>
      </defs>
      <circle cx="120" cy="120" r="100" fill="url(#logo-bg)" />
      <path
        d="M68 78C68 67.5066 76.5066 59 87 59H153C163.493 59 172 67.5066 172 78V126C172 136.493 163.493 145 153 145H116L91 167V145H87C76.5066 145 68 136.493 68 126V78Z"
        fill="#F9FAFB"
        opacity="0.95"
      />
      <circle cx="98" cy="101" r="7" fill="url(#logo-accent)" />
      <circle cx="120" cy="90" r="7" fill="url(#logo-accent)" />
      <circle cx="143" cy="106" r="7" fill="url(#logo-accent)" />
      <circle cx="118" cy="122" r="7" fill="url(#logo-accent)" />
      <path
        d="M98 101L120 90L143 106L118 122L98 101Z"
        stroke="#CBD5E1"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 90L118 122"
        stroke="#CBD5E1"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M174 63L178 73L188 77L178 81L174 91L170 81L160 77L170 73L174 63Z"
        fill="#ffffff"
        opacity="0.9"
      />
    </svg>
  );
}

export function LogoIcon({className}: {className?: string}) {
  return (
    <svg
      className={className}
      width="24"
      height="24"
      viewBox="0 0 240 240"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient
          id="logo-icon-bg"
          x1="0"
          y1="0"
          x2="240"
          y2="240"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#E3032E" />
          <stop offset="1" stopColor="#B8022A" />
        </linearGradient>
        <linearGradient
          id="logo-icon-accent"
          x1="60"
          y1="60"
          x2="180"
          y2="180"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#fecdd3" />
        </linearGradient>
      </defs>
      <circle cx="120" cy="120" r="100" fill="url(#logo-icon-bg)" />
      <path
        d="M68 78C68 67.5066 76.5066 59 87 59H153C163.493 59 172 67.5066 172 78V126C172 136.493 163.493 145 153 145H116L91 167V145H87C76.5066 145 68 136.493 68 126V78Z"
        fill="#F9FAFB"
        opacity="0.95"
      />
      <circle cx="98" cy="101" r="7" fill="url(#logo-icon-accent)" />
      <circle cx="120" cy="90" r="7" fill="url(#logo-icon-accent)" />
      <circle cx="143" cy="106" r="7" fill="url(#logo-icon-accent)" />
      <circle cx="118" cy="122" r="7" fill="url(#logo-icon-accent)" />
      <path
        d="M98 101L120 90L143 106L118 122L98 101Z"
        stroke="#CBD5E1"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 90L118 122"
        stroke="#CBD5E1"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
