interface Source {
  gcs_name: string;
  name: string;
  industry: string;
  topics: string[];
  url?: string | null;
}

export default function SourceCard({ source }: { source: Source }) {
  const inner = (
    <div className="h-full rounded-lg border border-[#243340] bg-[#1C2B36] px-3 py-2 text-sm transition-colors hover:border-[#D9FF00]">
      <p className="font-medium text-[#e8e8e8] leading-snug truncate" title={source.name}>
        {source.name}
      </p>
      {source.industry && (
        <p className="text-[#D9FF00] text-xs mt-0.5">{source.industry}</p>
      )}
      {source.topics.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {source.topics.slice(0, 3).map((t) => (
            <span key={t} className="bg-[#243340] text-[#7B92A5] text-xs px-1.5 py-0.5 rounded">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );

  if (source.url) {
    return (
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="block h-full">
        {inner}
      </a>
    );
  }

  return inner;
}
