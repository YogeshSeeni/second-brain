import { Card, CardBody, CardHeader } from "@/components/ui/Card";

export function PlaceholderPage({
  title,
  note,
}: {
  title: string;
  note: string;
}) {
  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-2xl">
        <Card>
          <CardHeader title={title} subtitle="coming later this week" />
          <CardBody>
            <p className="text-sm text-zinc-400">{note}</p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
