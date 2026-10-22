import { TierLoader } from "@/components/motion";

export default function Loading() {
  return (
    <div className="grid flex-1 place-items-center">
      <TierLoader label="Loading" />
    </div>
  );
}
