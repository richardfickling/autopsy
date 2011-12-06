/*
 * Autopsy Forensic Browser
 *
 * Copyright 2011 Basis Technology Corp.
 * Contact: carrier <at> sleuthkit <dot> org
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.sleuthkit.autopsy.directorytree;

import org.openide.nodes.Children;
import org.sleuthkit.autopsy.datamodel.ImageNode;
import org.sleuthkit.autopsy.datamodel.VolumeNode;
import org.sleuthkit.autopsy.datamodel.DirectoryNode;
import org.openide.nodes.FilterNode;
import org.openide.nodes.Node;
import org.sleuthkit.datamodel.Directory;

/**
 * This class wraps around nodes that are displayed in the directory tree and 
 * hides files, '..', and other children that should not be displayed. 
 * 
 * @author jantonius
 */
class DirectoryTreeFilterChildren extends FilterNode.Children {

    /** the constructor */
    public DirectoryTreeFilterChildren(Node arg) {
        super(arg);
    }

    @Override
    protected Node copyNode(Node arg0) {
        return new DirectoryTreeFilterNode(arg0);
    }

    @Override
    protected Node[] createNodes(Node arg0) {
        // filter out the FileNode and the "." and ".." directories
        if (arg0 != null && (arg0 instanceof ImageNode
                || arg0 instanceof VolumeNode || (arg0 instanceof DirectoryNode
                && !((Directory) ((DirectoryNode) arg0).getContent()).getName().equals(".")
                && !((Directory) ((DirectoryNode) arg0).getContent()).getName().equals("..")))) {
            return new Node[]{this.copyNode(arg0)};
        } else {
            return new Node[]{};
        }
    }

    /**
     * Return the children based on the current node given. If the node doesn't
     * have any directory or volume or image node inside it, it just returns leaf.
     * 
     * @param arg        the node
     * @return children  the children
     */
    public static Children createInstance(Node arg) {
        return new DirectoryTreeFilterChildren(arg);
    }
}