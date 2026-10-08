// MIT. Resolve nested bounds bottom-up before the pinned renderer's top-down
// transform pass. This makes a sought frame independent of earlier seeks.
import { Host, Sequential, computeGroupBounds, computeLocalMatrix } from '@diffusionstudio/runtime';

export function settleGeometry(world: any, scene: any) {
  const visit = (node: any) => {
    if (!node?.native) return;
    // Sequences inherit their parent's box rather than fitting their children.
    if (node.entity.has(Sequential)) computeGroupBounds(world,node.entity);
    for (const child of node.children || []) visit(child);
    computeGroupBounds(world,node.entity);
    computeLocalMatrix(world,node.entity);
  };
  visit(scene.get(Host));
}
