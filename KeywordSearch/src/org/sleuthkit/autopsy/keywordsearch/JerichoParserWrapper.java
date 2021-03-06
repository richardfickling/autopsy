/*
 * Autopsy Forensic Browser
 *
 * Copyright 2012 Basis Technology Corp.
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
package org.sleuthkit.autopsy.keywordsearch;

import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import java.util.logging.Level;
import org.sleuthkit.autopsy.coreutils.Logger;
import net.htmlparser.jericho.Attributes;
import net.htmlparser.jericho.Source;
import net.htmlparser.jericho.StartTag;
import net.htmlparser.jericho.StartTagType;
import net.htmlparser.jericho.TextExtractor;

/**
 * Uses Jericho HTML Parser to create a Reader for output, consisting of
 * the text, comments, tag attributes, and other important information
 * found in the HTML.
 */
public class JerichoParserWrapper {
    private static final Logger logger = Logger.getLogger(JerichoParserWrapper.class.getName());
    private InputStream in;    
    private StringBuilder out;
    private Reader reader;
    
    JerichoParserWrapper(InputStream in) {
        this.in = in;
    }
    
    /**
     * Initialize the reader by parsing the InputStream, adding it to StringBuilder,
     * and creating a StringReader from it.
     */
    public void parse() {
        out = new StringBuilder();
        
        try {
            Source source = new Source(in);
            source.fullSequentialParse();
            
            StringBuilder text = new StringBuilder();
            StringBuilder scripts = new StringBuilder();
            StringBuilder links = new StringBuilder();
            StringBuilder images = new StringBuilder();
            StringBuilder comments = new StringBuilder();
            StringBuilder others = new StringBuilder();
            int numScripts = 1;
            int numLinks = 1;
            int numImages = 1;
            int numComments = 1;
            int numOthers = 1;

            // Extract text from the source
            TextExtractor extractor = new TextExtractor(source);
            // Split it at every ". " but keep the .
            String[] lines = extractor.toString().split("(?<=\\. )");
            for(String s : lines) {
                text.append(s).append("\n");
            }

            // Get all the tags in the source
            List<StartTag> tags = source.getAllStartTags();
            for(StartTag tag : tags) {
                if(tag.getName().equals("script")) {
                    // If the <script> tag has attributes
                    scripts.append(numScripts).append(") ");
                    if(tag.getTagContent().length()>0) {
                        scripts.append(tag.getTagContent()).append(" ");
                    }
                    // Get whats between the <script> .. </script> tags
                    scripts.append(tag.getElement().getContent()).append("\n");
                    numScripts++;
                } else if(tag.getName().equals("a")) {
                    links.append(numLinks).append(") ");
                    links.append(tag.getTagContent()).append("\n");
                    numLinks++;
                } else if(tag.getName().equals("img")) {
                    images.append(numImages).append(") ");
                    images.append(tag.getTagContent()).append("\n");
                    numImages++;
                } else if(tag.getTagType().equals(StartTagType.COMMENT)) {
                    comments.append(numComments).append(") ");
                    comments.append(tag.getTagContent()).append("\n");
                    numComments++;
                } else {
                    // Make sure it has an attribute
                    Attributes atts = tag.getAttributes();
                    if (atts!=null && atts.length()>0) {
                        others.append(numOthers).append(") ");
                        others.append(tag.getName()).append(":");
                        others.append(tag.getTagContent()).append("\n");
                        numOthers++;
                    }
                }
            }

            out.append(text.toString()).append("\n");

            out.append("----------NONVISIBLE TEXT----------\n\n");
            if(numScripts>1) {
                out.append("---Scripts---\n");
                out.append(scripts.toString()).append("\n");
            } if(numLinks>1) {
                out.append("---Links---\n");
                out.append(links.toString()).append("\n");
            } if(numImages>1) {
                out.append("---Images---\n");
                out.append(images.toString()).append("\n");
            } if(numComments>1) {
                out.append("---Comments---\n");
                out.append(comments.toString()).append("\n");
            } if(numOthers>1) {
                out.append("---Others---\n");
                out.append(others.toString()).append("\n");
            }
            // All done, now make it a reader
            reader = new StringReader(out.toString());
        } catch (IOException ex) {
            logger.log(Level.WARNING, "Unable to parse the HTML file", ex);
        }
    }
    
    /**
     * Returns the reader, initialized in parse(), which will be
     * null if parse() is not called or if parse() throws an error.
     * @return Reader
     */
    public Reader getReader() {
        return reader;
    }
    
}
