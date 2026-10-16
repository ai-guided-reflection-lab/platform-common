import React, { useId } from "react";

// Decorative, scalable artwork; no remote image or font dependency.
export default function LearningArtwork() {
  const id = useId().replaceAll(":", "");
  return (
    <svg
      className="learning-artwork"
      viewBox="0 0 380 180"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={`${id}-leaf`} x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#b5d0b9" />
          <stop offset="1" stopColor="#558f7d" />
        </linearGradient>
        <linearGradient
          id={`${id}-book`}
          x1="170"
          y1="115"
          x2="260"
          y2="175"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#90b7a3" />
          <stop offset="1" stopColor="#407e6d" />
        </linearGradient>
      </defs>
      <path
        d="M40 159c-15-28 12-40 35-30-12-36 15-50 40-28 7-33 40-39 55-11 17-24 36-19 48 0 10-39 37-45 60-16 26-16 43 0 40 20 41-13 62 21 35 42 5 13-3 25-20 25H40Z"
        fill="#eaf1e8"
        opacity=".65"
      />
      <path
        d="M86 165c0-31-22-56-34-79m35 63c10-28 7-67 13-99m16 115c-12-42 7-84 28-127m-12 107c18-35 25-81 31-121m-2 141c-10-39 17-72 31-99m104 98c-8-35-9-65 0-101m-6 83c14-23 31-38 45-59m-22 78c16-20 22-36 29-57"
        stroke="#87b29d"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <g fill={`url(#${id}-leaf)`} opacity=".8">
        <path d="M68 119C44 114 43 91 38 77c22 13 37 23 30 42Z" />
        <path d="M83 141c-15-1-22-13-26-25 19 4 28 8 26 25Z" />
        <path d="M98 89c-21-10-17-32-13-45 12 18 21 29 13 45Z" />
        <path d="M98 115c17-13 23-29 17-42-17 12-25 27-17 42Z" />
        <path d="M134 79c-14-19-4-37 9-49 1 21 5 35-9 49Z" />
        <path d="M122 117c-20-13-17-32-14-44 17 16 25 28 14 44Z" />
        <path d="M148 100c22-8 27-28 25-42-21 11-28 23-25 42Z" />
        <path d="M161 57c-6-24 7-34 22-46-1 21-4 38-22 46Z" />
        <path d="M178 115c-4-22 9-38 24-45-5 21-8 35-24 45Z" />
        <path d="M292 96c-18-11-21-28-15-45 14 17 23 28 15 45Z" />
        <path d="M296 119c17-8 24-27 19-40-15 10-24 21-19 40Z" />
        <path d="M312 124c21-1 30-16 31-32-19 4-31 14-31 32Z" />
        <path d="M320 151c16 6 32-3 39-16-20-3-33 1-39 16Z" />
      </g>
      <g fill="#cadcc9" opacity=".65">
        <path d="M255 123c-21-8-22-25-20-40 17 13 27 22 20 40Z" />
        <path d="M267 104c-5-20 4-37 16-43 0 20-1 34-16 43Z" />
        <path d="M317 78c-11-13-11-28-3-42 10 16 15 28 3 42Z" />
        <path d="M329 101c-3-17 9-29 22-32-4 17-10 28-22 32Z" />
      </g>
      <ellipse cx="218" cy="166" rx="109" ry="5" fill="#dbe7de" />
      <path
        d="M133 142h139c10 0 15 24 5 28H132c-15 0-14-28 1-28Z"
        fill={`url(#${id}-book)`}
      />
      <path
        d="M141 147h119c-5 5-6 12-1 18H141c-9 0-9-18 0-18Z"
        fill="#f5f6eb"
      />
      <path
        d="M143 152h111m-111 5h109m-109 4h112"
        stroke="#c6d7c9"
        strokeWidth=".8"
      />
      <path
        d="M160 117h112c13 0 15 25 1 25H160c5-7 5-17 0-25Z"
        fill="#87af9a"
      />
      <path d="M164 122h97c7 0 7 15 0 15h-97c3-5 3-10 0-15Z" fill="#fbfbf1" />
      <path d="M169 126h90m-90 5h90" stroke="#c6d7c9" strokeWidth=".8" />
      <path
        d="M170 112h105"
        stroke="#639680"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M19 169h342"
        stroke="#a9cbbc"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
